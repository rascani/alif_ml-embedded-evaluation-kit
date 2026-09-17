# SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates
# <open-source-office@arm.com>
# SPDX-License-Identifier: Apache-2.0
"""Choose CMSIS-NN int8 registrations only for compatible model-wide signatures."""

from pathlib import Path
import re

from ethosu.vela.tflite.BuiltinOperator import BuiltinOperator
from ethosu.vela.tflite.Model import Model
from ethosu.vela.tflite.Operator import Operator
from ethosu.vela.tflite.SubGraph import SubGraph
from ethosu.vela.tflite.TensorType import TensorType

INT8_HEADERS = {
    "ADD": "add.h",
    "AVERAGE_POOL_2D": "pooling.h",
    "CONV_2D": "conv.h",
    "DEPTHWISE_CONV_2D": "depthwise_conv.h",
    "FULLY_CONNECTED": "fully_connected.h",
    "SOFTMAX": "softmax.h",
}


def tensor_types(graph: SubGraph, indices: list[int], optional: bool) -> list[str]:
    """Read tensor types and reject dangling indices rather than inferring a signature.

    :param graph:       Subgraph owning the tensors.
    :param indices:     Operator input or output tensor indices.
    :param optional:    Whether the absent-input sentinel is permitted.
    :returns:           Schema type names, or ABSENT for optional input -1.
    :raises ValueError: If a tensor index is outside the subgraph.
    """
    names = {value: name for name, value in vars(TensorType).items() if isinstance(value, int)}
    result = []
    for index in indices:
        if index == -1 and optional:
            result.append("ABSENT")
        elif 0 <= index < graph.TensorsLength():
            result.append(names.get(graph.Tensors(index).Type(), "UNKNOWN"))
        else:
            raise ValueError(f"Invalid tensor index {index}")
    return result


def node_signature(graph: SubGraph, node: Operator) -> dict:
    """Record the complete input/output type signature, including bias/shape tensors.

    :param graph:   Subgraph owning the operator.
    :param node:    Operator to inspect.
    :returns:       Input and output type names.
    """
    return {
        "inputs": tensor_types(graph, [node.Inputs(i) for i in range(node.InputsLength())], True),
        "outputs": tensor_types(
            graph, [node.Outputs(i) for i in range(node.OutputsLength())], False
        ),
    }


def model_signatures(model_data: bytes) -> dict[str, list[dict]]:
    """Collect every used node's signature, including nodes in secondary subgraphs.

    :param model_data:  Flatbuffer already checked by get_model_operators.
    :returns:           Builtin names mapped to unique type signatures.
    """
    model = Model.GetRootAs(model_data, 0)
    names = {value: name for name, value in vars(BuiltinOperator).items() if isinstance(value, int)}
    signatures: dict[str, list[dict]] = {}
    for graph_index in range(model.SubgraphsLength()):
        graph = model.Subgraphs(graph_index)
        for node_index in range(graph.OperatorsLength()):
            node = graph.Operators(node_index)
            code = model.OperatorCodes(node.OpcodeIndex())
            name = names[max(code.BuiltinCode(), code.DeprecatedBuiltinCode())]
            signature = node_signature(graph, node)
            used = signatures.setdefault(name, [])
            if signature not in used:
                used.append(signature)
    return signatures


def compatible_int8(name: str, signature: dict) -> bool:
    """Recognize the activation/weight/bias combinations supported by narrow kernels.

    :param name:        Builtin operator name.
    :param signature:   Input and output type names.
    :returns:           Whether selecting this operator's int8 registration is safe.
    """
    inputs = signature["inputs"]
    if signature["outputs"] != ["INT8"]:
        return False
    if name in ("CONV_2D", "DEPTHWISE_CONV_2D", "FULLY_CONNECTED"):
        return (len(inputs) in (2, 3) and inputs[:2] == ["INT8", "INT8"]
                and (len(inputs) == 2 or inputs[2] in ("INT32", "ABSENT")))
    if name == "ADD":
        return inputs == ["INT8", "INT8"]
    if name in ("AVERAGE_POOL_2D", "SOFTMAX"):
        return inputs == ["INT8"]
    return False


def select_registration(name: str, signatures: list[dict], kernels: Path) -> dict:
    """Select an available narrow registration, otherwise retain the generic operator.

    :param name:        Builtin name.
    :param signatures:  Every signature used by that builtin in the model.
    :param kernels:     Header directory in the selected TFLM checkout.
    :returns:           Registration choice and a reason for the manifest.
    """
    generic = {"registration": None, "backend": "generic", "signatures": signatures}
    if name not in INT8_HEADERS:
        return dict(generic, reason="no_int8_specialization")
    if not signatures or not all(compatible_int8(name, item) for item in signatures):
        return dict(generic, reason="incompatible_or_mixed_signatures")
    registration = f"Register_{name}_INT8"
    header = kernels / INT8_HEADERS[name]
    if not header.exists() or not re.search(
        rf"\bTFLMRegistration\s+{registration}\s*\(", header.read_text(encoding="utf-8")
    ):
        return dict(generic, reason="registration_unavailable")
    return {
        "registration": registration, "backend": "CMSIS_NN",
        "reason": "all_nodes_compatible_int8", "signatures": signatures,
    }
