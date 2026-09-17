# SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates
# <open-source-office@arm.com>
# SPDX-License-Identifier: Apache-2.0
"""Generate a model-specific TFLM inference runner from a flatbuffer and resolver API."""

import argparse
import hashlib
import json
import re
from pathlib import Path

from ethosu.vela.tflite.BuiltinOperator import BuiltinOperator
from ethosu.vela.tflite.Model import Model
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from mlek_tools.gen.tflm_registration import model_signatures, select_registration


def get_model_operators(model_data: bytes) -> dict[str, list[int]]:
    """Collect unique builtin operators and versions used across all subgraphs.

    :param model_data:  Serialized TFLite model.
    :returns:           Operator names mapped to their used versions.
    :raises ValueError: If the model uses custom or unknown operators.
    """
    if not Model.ModelBufferHasIdentifier(model_data, 0):
        raise ValueError("Expected a TFLite flatbuffer with the TFL3 identifier")
    model = Model.GetRootAs(model_data, 0)
    names = {value: name for name, value in vars(BuiltinOperator).items()
             if isinstance(value, int)}
    operators: dict[str, set[int]] = {}
    for subgraph_index in range(model.SubgraphsLength()):
        subgraph = model.Subgraphs(subgraph_index)
        for operator_index in range(subgraph.OperatorsLength()):
            opcode_index = subgraph.Operators(operator_index).OpcodeIndex()
            if opcode_index >= model.OperatorCodesLength():
                raise ValueError(f"Invalid operator code index {opcode_index}")
            opcode = model.OperatorCodes(opcode_index)
            code = max(opcode.BuiltinCode(), opcode.DeprecatedBuiltinCode())
            if code == BuiltinOperator.CUSTOM:
                raise ValueError(
                    f"Custom operator {opcode.CustomCode()!r} is not supported by the "
                    "selective TFLM runner; provide a custom resolver for this model"
                )
            if code not in names:
                raise ValueError(f"Unknown builtin operator code {code}")
            operators.setdefault(names[code], set()).add(opcode.Version())
    return {name: sorted(versions) for name, versions in sorted(operators.items())}


def get_registration_methods(resolver_header: str) -> dict[str, str]:
    """Read builtin-to-Add-method mappings from the selected TFLM checkout.

    :param resolver_header: Contents of micro_mutable_op_resolver.h.
    :returns:               Builtin names mapped to resolver method names.
    """
    methods = {}
    # Inspect the function body rather than guessing capitalization (e.g. LSTM,
    # CUMSUM, BATCH_MATMUL). Unrecognized APIs fail during generation below.
    functions = re.findall(
        r"TfLiteStatus (Add\w+)\([^{}]*\)\s*\{(.*?)\n  \}",
        resolver_header, re.DOTALL,
    )
    for method, body in functions:
        builtin = re.search(r"\bAddBuiltin\(\s*BuiltinOperator_(\w+)", body)
        if builtin:
            methods[builtin.group(1)] = method
    return methods


def generate_resolver(
    model_path: Path, resolver_path: Path, output_dir: Path, select_int8: bool = False
):
    """Write the selected model wrapper and an operator manifest.

    :param model_path:      Model to embed in the inference runner.
    :param resolver_path:   TFLM resolver header defining available Add methods.
    :param output_dir:      Destination for the generated header and JSON manifest.
    :param select_int8:     Select compatible CMSIS-NN int8 registrations.
    :raises ValueError:     If a required operator has no TFLM registration method.
    """
    model_data = model_path.read_bytes()
    operators = get_model_operators(model_data)
    methods = get_registration_methods(resolver_path.read_text(encoding="utf-8"))
    unsupported = sorted(operators.keys() - methods.keys())
    if unsupported:
        raise ValueError(f"No TFLM resolver registration for: {', '.join(unsupported)}")
    selected = [{"builtin": name, "versions": versions, "method": methods[name]}
                for name, versions in operators.items()]
    signatures = model_signatures(model_data) if select_int8 else {}
    for operator in selected:
        choice = select_registration(
            operator["builtin"], signatures.get(operator["builtin"], []),
            resolver_path.parent / "kernels",
        ) if select_int8 else {
            "registration": None, "backend": "generic", "reason": "selection_disabled",
            "signatures": [],
        }
        operator.update(choice)
    manifest = {
        "model_sha256": hashlib.sha256(model_data).hexdigest(),
        "operator_count": len(selected),
        "resolver_capacity": max(1, len(selected)),
        "int8_selection_enabled": select_int8,
        "operators": selected,
    }
    env = Environment(
        loader=FileSystemLoader(Path(__file__).parent / "templates"),
        undefined=StrictUndefined, trim_blocks=True, lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    header = env.get_template("SelectedTflmModel.hpp.template").render(**manifest)
    (output_dir / "SelectedTflmModel.hpp").write_text(header, encoding="utf-8")
    (output_dir / "selected_tflm_operators.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Selected {len(selected)} TFLM operators: {', '.join(operators)}")


def main():
    """Parse paths and generate the model-specific resolver."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--resolver-header", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--select-int8", action="store_true")
    args = parser.parse_args()
    generate_resolver(args.model_path, args.resolver_header, args.output_dir, args.select_int8)


if __name__ == "__main__":
    main()
