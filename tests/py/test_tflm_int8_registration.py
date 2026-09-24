# SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates
# <open-source-office@arm.com>
# SPDX-License-Identifier: Apache-2.0
"""Check signature-dependent registration using small, independently built flatbuffers."""

import json
from pathlib import Path
import tempfile
import unittest

import flatbuffers
from ethosu.vela.tflite import Model, Operator, SubGraph, Tensor
from ethosu.vela.tflite.BuiltinOperator import BuiltinOperator
from ethosu.vela.tflite.TensorType import TensorType

from mlek_tools.gen.gen_tflm_resolver import generate_resolver
from mlek_tools.gen.tflm_registration import compatible_int8, model_signatures
from test_gen_tflm_resolver import RESOLVER, build_operator_codes


def typed_node(
    builder: flatbuffers.Builder, signatures: tuple[list[int | None], list[int]]
) -> tuple[int, list[int]]:
    """Build an operator with tensor types and an optional absent-input sentinel.

    :param builder:     Flatbuffer under construction.
    :param signatures:  Input/output schema tensor types.
    :returns:           Operator offset and tensor offsets.
    """
    tensors = []
    vectors = []
    for types in signatures:
        indices = []
        for tensor_type in types:
            if tensor_type is None:
                indices.append(-1)
            else:
                indices.append(len(tensors))
                Tensor.Start(builder)
                Tensor.AddType(builder, tensor_type)
                tensors.append(Tensor.End(builder))
        builder.StartVector(4, len(indices), 4)
        for index in reversed(indices):
            builder.PrependInt32(index)
        vectors.append(builder.EndVector())
    Operator.Start(builder)
    Operator.AddInputs(builder, vectors[0])
    Operator.AddOutputs(builder, vectors[1])
    return Operator.End(builder), tensors


def typed_model(builtin: int, signatures: list[tuple[list[int | None], list[int]]]) -> bytes:
    """Build one node per subgraph, all sharing a builtin registration.

    :param builtin:     Builtin operator code.
    :param signatures:  Input/output types for each subgraph's node.
    :returns:           Serialized TFLite model with tensor metadata.
    """
    builder = flatbuffers.Builder(1024)
    codes = build_operator_codes(builder, [(builtin, builtin, 1)])
    graphs = []
    for signature in signatures:
        node, tensors = typed_node(builder, signature)
        SubGraph.StartTensorsVector(builder, len(tensors))
        for tensor in reversed(tensors):
            builder.PrependUOffsetTRelative(tensor)
        tensor_vector = builder.EndVector()
        SubGraph.StartOperatorsVector(builder, 1)
        builder.PrependUOffsetTRelative(node)
        nodes = builder.EndVector()
        SubGraph.Start(builder)
        SubGraph.AddTensors(builder, tensor_vector)
        SubGraph.AddOperators(builder, nodes)
        graphs.append(SubGraph.End(builder))
    Model.StartSubgraphsVector(builder, len(graphs))
    for graph in reversed(graphs):
        builder.PrependUOffsetTRelative(graph)
    subgraphs = builder.EndVector()
    Model.Start(builder)
    Model.AddVersion(builder, 3)
    Model.AddOperatorCodes(builder, codes)
    Model.AddSubgraphs(builder, subgraphs)
    builder.Finish(Model.End(builder), file_identifier=b"TFL3")
    return bytes(builder.Output())


class Int8RegistrationTests(unittest.TestCase):
    """Reject unsafe narrowing while allowing int32 bias and optional bias inputs."""

    def test_int8_bias_signatures_and_mixed_subgraphs(self):
        """Every node must qualify; a later int16 or int4 node requires generic dispatch."""
        int8, int32 = TensorType.INT8, TensorType.INT32
        cases = (
            ([([int8, int8, int32], [int8]), ([int8, int8, None], [int8])], True),
            ([([int8, int8], [int8])], True),
            ([([int8, int8, int32], [int8]),
              ([TensorType.INT16, int8, TensorType.INT64], [TensorType.INT16])], False),
            ([([int8, int8, int32], [int8]), ([int8, TensorType.INT4, int32], [int8])], False),
        )
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            model = output / "test.tflite"
            for signatures, specialized in cases:
                with self.subTest(signatures=signatures):
                    model.write_bytes(typed_model(BuiltinOperator.FULLY_CONNECTED, signatures))
                    generate_resolver(model, RESOLVER, output, select_int8=True)
                    metadata = json.loads((output / "selected_tflm_operators.json").read_text())
                    choice = metadata["operators"][0]
                    expected = "Register_FULLY_CONNECTED_INT8" if specialized else None
                    self.assertEqual(choice["registration"], expected)
                    self.assertEqual(metadata["resolver_capacity"], 1)
                    header = (output / "SelectedTflmModel.hpp").read_text()
                    self.assertEqual("#if defined(CMSIS_NN)" in header, specialized)

    def test_non_int8_outputs_bias_and_arities_remain_generic(self):
        """Do not narrow int16-output softmax, unsupported bias types or malformed arities."""
        for name, inputs, outputs in (
            ("SOFTMAX", ["INT8"], ["INT16"]),
            ("CONV_2D", ["INT8", "INT8", "INT64"], ["INT8"]),
            ("DEPTHWISE_CONV_2D", ["INT8", "INT4", "INT32"], ["INT8"]),
            ("ADD", ["INT8", "FLOAT32"], ["INT8"]),
            ("AVERAGE_POOL_2D", [], ["INT8"]),
            ("RESHAPE", ["INT8", "INT32"], ["INT8"]),
        ):
            with self.subTest(name=name, inputs=inputs):
                self.assertFalse(compatible_int8(name, {"inputs": inputs, "outputs": outputs}))

    def test_missing_api_and_explicit_disable(self):
        """An older backend's missing declaration and an explicit opt-out both stay generic."""
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            model = output / "test.tflite"
            model.write_bytes(typed_model(BuiltinOperator.SOFTMAX,
                                          [([TensorType.INT8], [TensorType.INT8])]))
            resolver = output / "resolver.h"
            resolver.write_text(RESOLVER.read_text())
            generate_resolver(model, resolver, output, select_int8=True)
            metadata = json.loads((output / "selected_tflm_operators.json").read_text())
            self.assertEqual(metadata["operators"][0]["reason"], "registration_unavailable")
            generate_resolver(model, RESOLVER, output, select_int8=False)
            metadata = json.loads((output / "selected_tflm_operators.json").read_text())
            self.assertEqual(metadata["operators"][0]["reason"], "selection_disabled")

    def test_invalid_tensor_indices_fail(self):
        """Fail on missing tensors, including -1 in output rather than an optional input."""
        original = typed_model(BuiltinOperator.SOFTMAX, [([TensorType.INT8], [TensorType.INT8])])
        for inputs, value in ((True, 99), (True, -2), (False, -1)):
            data = bytearray(original)
            node = Model.Model.GetRootAs(data).Subgraphs(0).Operators(0)
            vector = node.InputsAsNumpy() if inputs else node.OutputsAsNumpy()
            vector[0] = value
            with self.subTest(inputs=inputs, value=value), self.assertRaisesRegex(
                ValueError, "Invalid tensor index"
            ):
                model_signatures(data)


if __name__ == "__main__":
    unittest.main()
