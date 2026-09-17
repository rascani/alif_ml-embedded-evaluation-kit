# SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates
# <open-source-office@arm.com>
# SPDX-License-Identifier: Apache-2.0
"""Tests for extracting model operators and generating selective TFLM resolvers."""

import json
import tempfile
import unittest
from pathlib import Path

import flatbuffers
from ethosu.vela.tflite import Model, Operator, OperatorCode, SubGraph
from ethosu.vela.tflite.BuiltinOperator import BuiltinOperator

from mlek_tools.gen.gen_tflm_resolver import (
    generate_resolver,
    get_model_operators,
    get_registration_methods,
)

ROOT = Path(__file__).resolve().parents[2]
RESOLVER = ROOT / "dependencies/tensorflow/tensorflow/lite/micro/micro_mutable_op_resolver.h"


def build_operator_codes(builder: flatbuffers.Builder, opcodes: list[tuple[int, int, int]]) -> int:
    """Build an operator-code vector using the generated schema API.

    :param builder: Flatbuffer builder receiving the vector.
    :param opcodes: Builtin code, deprecated code, and version triples.
    :returns:       Offset of the completed operator-code vector.
    """
    custom_name = builder.CreateString("UnsupportedCustom")
    code_offsets = []
    for builtin, deprecated, version in opcodes:
        OperatorCode.Start(builder)
        OperatorCode.AddBuiltinCode(builder, builtin)
        OperatorCode.AddDeprecatedBuiltinCode(builder, deprecated)
        OperatorCode.AddVersion(builder, version)
        if builtin == BuiltinOperator.CUSTOM:
            OperatorCode.AddCustomCode(builder, custom_name)
        code_offsets.append(OperatorCode.End(builder))
    Model.StartOperatorCodesVector(builder, len(code_offsets))
    for offset in reversed(code_offsets):
        builder.PrependUOffsetTRelative(offset)
    return builder.EndVector()


def build_model(opcodes: list[tuple[int, int, int]], subgraphs: list[list[int]]) -> bytes:
    """Build a small flatbuffer with operator tables for parser tests.

    :param opcodes:     Builtin code, deprecated code, and version triples.
    :param subgraphs:   Operator-code indices used by each subgraph.
    :returns:           A serialized model, without inference tensors or buffers.
    """
    builder = flatbuffers.Builder(1024)
    codes = build_operator_codes(builder, opcodes)

    graph_offsets = []
    for graph in subgraphs:
        op_offsets = []
        for index in graph:
            Operator.Start(builder)
            Operator.AddOpcodeIndex(builder, index)
            op_offsets.append(Operator.End(builder))
        SubGraph.StartOperatorsVector(builder, len(op_offsets))
        for offset in reversed(op_offsets):
            builder.PrependUOffsetTRelative(offset)
        operators = builder.EndVector()
        SubGraph.Start(builder)
        SubGraph.AddOperators(builder, operators)
        graph_offsets.append(SubGraph.End(builder))
    Model.StartSubgraphsVector(builder, len(graph_offsets))
    for offset in reversed(graph_offsets):
        builder.PrependUOffsetTRelative(offset)
    graphs = builder.EndVector()
    Model.Start(builder)
    Model.AddVersion(builder, 3)
    Model.AddOperatorCodes(builder, codes)
    Model.AddSubgraphs(builder, graphs)
    builder.Finish(Model.End(builder), file_identifier=b"TFL3")
    return bytes(builder.Output())


class ResolverGenerationTests(unittest.TestCase):
    """Exercise subgraphs, schema compatibility, rejection, and generated capacity."""

    def test_subgraphs_versions_and_unused_opcodes(self):
        """Deduplicate operators across subgraphs and ignore unused custom opcodes."""
        fc = BuiltinOperator.FULLY_CONNECTED
        softmax = BuiltinOperator.SOFTMAX
        custom = BuiltinOperator.CUSTOM
        data = build_model([(fc, fc, 1), (fc, fc, 4), (softmax, softmax, 2),
                            (custom, custom, 1)], [[0, 0], [1, 2]])
        self.assertEqual(get_model_operators(data), {"FULLY_CONNECTED": [1, 4], "SOFTMAX": [2]})

    def test_legacy_and_extended_builtin_codes(self):
        """Honor the deprecated field and builtin codes above the int8 range."""
        data = build_model([(0, BuiltinOperator.FULLY_CONNECTED, 4),
                            (BuiltinOperator.GELU, 127, 1)], [[0, 1]])
        self.assertEqual(get_model_operators(data), {"FULLY_CONNECTED": [4], "GELU": [1]})

    def test_custom_operator_is_rejected(self):
        """Fail clearly instead of silently omitting a required custom kernel."""
        custom = BuiltinOperator.CUSTOM
        with self.assertRaisesRegex(ValueError, "UnsupportedCustom"):
            get_model_operators(build_model([(custom, custom, 1)], [[0]]))

    def test_invalid_opcode_index_is_rejected(self):
        """Reject an operator pointing outside the opcode table."""
        with self.assertRaisesRegex(ValueError, "Invalid operator code index"):
            get_model_operators(build_model([], [[0]]))

    def test_invalid_identifier_is_rejected(self):
        """Reject other flatbuffer formats before traversing their tables."""
        with self.assertRaisesRegex(ValueError, "TFL3"):
            get_model_operators(b"\0" * 16)

    def test_method_names_follow_the_selected_header(self):
        """Handle registration names whose capitalization cannot be guessed."""
        methods = get_registration_methods(RESOLVER.read_text(encoding="utf-8"))
        self.assertEqual(methods["CUMSUM"], "AddCumSum")
        self.assertEqual(methods["BATCH_MATMUL"], "AddBatchMatMul")
        self.assertEqual(methods["UNIDIRECTIONAL_SEQUENCE_LSTM"], "AddUnidirectionalSequenceLSTM")

    def test_generation_replacement_and_empty_graph(self):
        """Replacing a model updates capacity, calls, and its identifying hash."""
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            model = output / "model.tflite"
            relu = BuiltinOperator.RELU
            fc = BuiltinOperator.FULLY_CONNECTED
            model.write_bytes(build_model([(relu, relu, 1), (fc, fc, 4)], [[0, 1]]))
            generate_resolver(model, RESOLVER, output)
            first = json.loads((output / "selected_tflm_operators.json").read_text())
            header = (output / "SelectedTflmModel.hpp").read_text()
            self.assertEqual(first["resolver_capacity"], 2)
            self.assertIn("m_opResolver.AddRelu()", header)
            self.assertIn("m_opResolver.AddFullyConnected()", header)

            model.write_bytes(build_model([], [[]]))
            generate_resolver(model, RESOLVER, output)
            second = json.loads((output / "selected_tflm_operators.json").read_text())
            self.assertNotEqual(first["model_sha256"], second["model_sha256"])
            self.assertEqual(second["operator_count"], 0)
            self.assertEqual(second["resolver_capacity"], 1)
            self.assertNotIn("m_opResolver.Add", (output / "SelectedTflmModel.hpp").read_text())

    def test_unsupported_builtin_is_rejected(self):
        """A missing resolver API must fail generation before compilation."""
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            model = output / "model.tflite"
            densify = BuiltinOperator.DENSIFY
            model.write_bytes(build_model([(densify, min(densify, 127), 1)], [[0]]))
            with self.assertRaisesRegex(ValueError, "No TFLM resolver registration for: DENSIFY"):
                generate_resolver(model, RESOLVER, output)


if __name__ == "__main__":
    unittest.main()
