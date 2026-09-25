#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates
# <open-source-office@arm.com>
# SPDX-License-Identifier: Apache-2.0
"""Quantize the validated reference ResNet8 through the native Cortex-M stack."""

import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import importlib.metadata
import json
from pathlib import Path
import subprocess

import numpy as np
import torch
from executorch.backends.cortex_m.edge_compile_config import (
    cortex_m_edge_compile_config,
)
from executorch.backends.cortex_m.passes.cortex_m_pass_manager import CortexMPassManager
from executorch.backends.cortex_m.quantizer.quantizer import CortexMQuantizer
from executorch.backends.cortex_m.target_config import CortexMTargetConfig
from executorch.exir import to_edge_transform_and_lower
from executorch.exir._serialize._program import deserialize_pte_binary
from executorch.exir.passes.quantize_io_pass import QuantizeInputs, QuantizeOutputs
from executorch.exir.schema import KernelCall, ScalarType, Tensor
from reference_model import load_reference_model, NHWCInput
from torchao.quantization.pt2e.quantize_pt2e import convert_pt2e, prepare_pt2e
from validation_metrics import accuracy


def quantization_info(args):
    scale, zero_point, quant_min, quant_max, dtype = args
    return {
        "scale": float(scale),
        "zero_point": int(zero_point),
        "quant_min": int(quant_min),
        "quant_max": int(quant_max),
        "dtype": str(dtype).removeprefix("torch."),
    }


def build_program(reference_dir, images, calibration):
    torch.set_num_threads(2)
    torch.use_deterministic_algorithms(True)
    model, epsilon_changes = load_reference_model(reference_dir)
    model = NHWCInput(model).eval()
    example = (torch.from_numpy(images[:1].astype(np.float32)),)
    captured = torch.export.export(model, example, strict=True).module()
    prepared = prepare_pt2e(captured, CortexMQuantizer(use_explicit_layout=True))
    with torch.no_grad():
        for count, index in enumerate(calibration, 1):
            prepared(torch.from_numpy(images[index : index + 1].astype(np.float32)))
            if count % 100 == 0:
                print(f"Calibrated {count}/{len(calibration)}", flush=True)
    converted = convert_pt2e(prepared)
    edge = to_edge_transform_and_lower(
        torch.export.export(converted, example, strict=True),
        compile_config=cortex_m_edge_compile_config(),
    )
    qi = QuantizeInputs(edge, [0], method_name="forward")
    qo = QuantizeOutputs(edge, [0], method_name="forward")
    edge = edge.transform([qi, qo])
    input_info, output_info = quantization_info(qi.quant_args[0]), quantization_info(
        qo.dequant_args[0]
    )
    assert input_info["dtype"] == output_info["dtype"] == "int8"
    assert output_info["scale"] == 1 / 256 and output_info["zero_point"] == -128
    reference_program = deepcopy(edge.exported_program())
    target = CortexMTargetConfig.from_target_string("cortex-m55")
    edge._edge_programs["forward"] = CortexMPassManager(
        edge.exported_program(), target_config=target, use_explicit_layout=True
    ).transform()
    edge.exported_program().validate()
    return (
        edge,
        reference_program,
        qi.quant_args[0],
        input_info,
        output_info,
        epsilon_changes,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--reference-dir", type=Path, required=True)
    parser.add_argument("--float-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    float_report = json.loads((args.float_dir / "float-report.json").read_text())
    assert float_report["float_validation_passed"]
    assert (
        hashlib.sha256(
            (args.reference_dir / "keras_weights.npz").read_bytes()
        ).hexdigest()
        == float_report["source_weights_sha256"]
    )
    assert (
        hashlib.sha256(
            (args.reference_dir / "keras_model.json").read_bytes()
        ).hexdigest()
        == float_report["source_config_sha256"]
    )
    source_base = "9250dc3537862db4f66bac07a8974dad81cc0f20"
    source_patch = subprocess.check_output(
        ["git", "diff", "--binary", source_base, "--"]
    )
    (out / "source.patch").write_bytes(source_patch)
    dataset = np.load(args.data_dir / "cifar10.npz", allow_pickle=False)
    images, labels = dataset["images"], dataset["labels"]
    calibration, evaluation = (
        dataset["calibration_indices"],
        dataset["evaluation_indices"],
    )
    edge, reference_program, input_args, input_info, output_info, epsilon_changes = (
        build_program(args.reference_dir, images, calibration)
    )
    reference = reference_program.module(check_guards=False)
    (out / "quantized_edge.graph.txt").write_text(str(reference_program.graph) + "\n")
    lowered = edge.exported_program()
    lowered.validate()
    implementation = lowered.module(check_guards=False)
    (out / "resnet8.graph.txt").write_text(str(lowered.graph) + "\n")
    integer_inputs = torch.ops.quantized_decomposed.quantize_per_tensor.default(
        torch.from_numpy(images.astype(np.float32)), *input_args
    ).contiguous()

    reference_outputs = np.empty((len(images), 10), dtype=np.int8)
    with torch.no_grad():
        for index in range(len(images)):
            value = reference(integer_inputs[index : index + 1])
            if isinstance(value, (list, tuple)):
                value = value[0]
            assert value.dtype == torch.int8 and value.shape == (1, 10)
            reference_outputs[index] = value.numpy()[0]
            if (index + 1) % 1000 == 0:
                print(f"Quantized Edge reference {index + 1}/{len(images)}", flush=True)
    np.save(out / "quantized_edge.outputs.npy", reference_outputs)
    print("PT2E quantized accuracy:", accuracy(reference_outputs, dataset), flush=True)

    cortex_outputs = np.empty((len(evaluation), 1, 10), dtype=np.int8)
    with torch.no_grad():
        for count, index in enumerate(evaluation):
            value = implementation(integer_inputs[index : index + 1])
            if isinstance(value, (list, tuple)):
                value = value[0]
            assert value.dtype == torch.int8 and value.shape == (1, 10)
            cortex_outputs[count] = value.numpy()
    np.save(
        out / "resnet8.validation_inputs.npy",
        integer_inputs[evaluation].numpy()[:, None],
    )
    np.save(out / "resnet8.validation_outputs.npy", cortex_outputs)
    np.save(out / "resnet8.reference_outputs.npy", reference_outputs[evaluation, None])
    np.save(out / "evaluation_indices.npy", evaluation)
    np.save(out / "evaluation_labels.npy", labels[evaluation])
    integer_inputs[evaluation[0]].numpy().tofile(out / "resnet8.input.int8.bin")
    cortex_outputs[0].tofile(out / "resnet8.output.int8.bin")
    errors = np.abs(
        cortex_outputs[:, 0].astype(np.int32)
        - reference_outputs[evaluation].astype(np.int32)
    )
    cortex_accuracy = float(
        np.mean(cortex_outputs[:, 0].argmax(1) == labels[evaluation]) * 100
    )

    pte = edge.to_executorch().buffer
    (out / "resnet8.pte").write_bytes(pte)
    program = deserialize_pte_binary(pte).program
    plan = next(plan for plan in program.execution_plan if plan.name == "forward")
    assert not plan.delegates
    for indices in [plan.inputs, plan.outputs]:
        assert len(indices) == 1
        tensor = plan.values[indices[0]].val
        assert isinstance(tensor, Tensor) and tensor.scalar_type == ScalarType.CHAR
        assert tensor.dim_order == list(range(len(tensor.sizes)))
    operators = [f"{op.name}.{op.overload}" for op in plan.operators]
    calls = Counter(
        operators[ins.instr_args.op_index]
        for chain in plan.chains
        for ins in chain.instructions
        if isinstance(ins.instr_args, KernelCall)
    )
    assert calls == {
        "cortex_m::quantized_conv2d_nhwc.out": 9,
        "cortex_m::quantized_add.out": 3,
        "cortex_m::quantized_avg_pool2d_nhwc.out": 1,
        "cortex_m::quantized_linear.out": 1,
        "cortex_m::softmax.out": 1,
    }, calls
    input_info.update(shape=plan.values[plan.inputs[0]].val.sizes, layout="NHWC")
    output_info.update(shape=plan.values[plan.outputs[0]].val.sizes)
    cmsis = importlib.metadata.distribution("cmsis-nn")
    manifest = {
        "source_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip(),
        "source_base": source_base,
        "source_patch_sha256": hashlib.sha256(source_patch).hexdigest(),
        "keras_weights_sha256": float_report["source_weights_sha256"],
        "keras_config_sha256": float_report["source_config_sha256"],
        "torch": torch.__version__,
        "torchao": importlib.metadata.version("torchao"),
        "cmsis_nn_source": json.loads(cmsis.read_text("direct_url.json")),
        "target": "cortex-m55",
        "explicit_layout": True,
        "passes": [p.__name__ for p in CortexMPassManager.explicit_layout_pass_list],
        "weights": "Trained reference pretrainedResnet.h5, including its BatchNorm epsilon",
        "batchnorm_epsilon": epsilon_changes,
        "calibration": json.loads((args.data_dir / "dataset.json").read_text()),
        "validation_samples": len(evaluation),
        "models": {
            "resnet8": {
                "pte": "resnet8.pte",
                "bytes": len(pte),
                "sha256": hashlib.sha256(pte).hexdigest(),
                "input": input_info,
                "output": output_info,
                "runtime_operator_counts": dict(calls),
                "planned_nonconstant_buffer_sizes": plan.non_const_buffer_sizes,
                "quantized_edge_accuracy": accuracy(reference_outputs, dataset),
                "cortex_m_python": {
                    "samples": len(evaluation),
                    "reference_200_accuracy_percent": cortex_accuracy,
                    "max_error_steps_vs_edge": int(errors.max()),
                    "mean_error_steps_vs_edge": float(errors.mean()),
                    "top1_disagreements_vs_edge": int(
                        np.sum(
                            cortex_outputs[:, 0].argmax(1)
                            != reference_outputs[evaluation].argmax(1)
                        )
                    ),
                },
            }
        },
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(
        "Cortex-M Python accuracy:",
        cortex_accuracy,
        "Edge max error:",
        int(errors.max()),
        "PTE bytes:",
        len(pte),
        flush=True,
    )


if __name__ == "__main__":
    main()
