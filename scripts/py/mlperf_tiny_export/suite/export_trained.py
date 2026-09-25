#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates
# <open-source-office@arm.com>
# SPDX-License-Identifier: Apache-2.0
"""Export aligned, trained Tiny models with explicit layout and quantized I/O."""

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
from torchao.quantization.pt2e.quantize_pt2e import convert_pt2e, prepare_pt2e

from metrics import quality
from reference_models import load_reference_model, NHWCInput
from specs import MODELS


class IntegerGlobalPoolReference(torch.fx.Interpreter):
    def run_node(self, node):
        if (
            node.op != "call_function"
            or str(node.target) != "cortex_m.quantized_avg_pool2d_nhwc.default"
        ):
            return super().run_node(node)
        args, kwargs = self.fetch_args_kwargs_from_env(node)
        x, kernel, stride, padding, ceil_mode = args[:5]
        assert x.dtype == torch.int8 and tuple(kernel) == tuple(x.shape[1:3])
        assert padding == [0, 0] and not ceil_mode and not kwargs
        count = kernel[0] * kernel[1]
        total = x.to(torch.int32).sum(dim=(1, 2), keepdim=True)
        rounded = torch.div(
            total + torch.where(total > 0, count // 2, -(count // 2)),
            count,
            rounding_mode="trunc",
        )
        return rounded.clamp(-128, 127).to(torch.int8)


def quantization_info(args):
    scale, zero_point, quant_min, quant_max, dtype = args
    return {
        "scale": float(scale),
        "zero_point": int(zero_point),
        "quant_min": int(quant_min),
        "quant_max": int(quant_max),
        "dtype": str(dtype).removeprefix("torch."),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=MODELS, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--reference-dir", type=Path, required=True)
    parser.add_argument("--float-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--calibration-file", type=Path)
    parser.add_argument("--calibration-batch-size", type=int, default=1)
    args = parser.parse_args()
    torch.set_num_threads(2)
    torch.use_deterministic_algorithms(True)
    out = args.output_dir
    out.mkdir(parents=True, exist_ok=False)
    spec = MODELS[args.model]
    float_report = json.loads((args.float_dir / "float-report.json").read_text())
    assert float_report["float_validation_passed"]
    for filename, key in [
        ("keras_weights.npz", "source_weights_sha256"),
        ("keras_model.json", "source_config_sha256"),
    ]:
        assert (
            hashlib.sha256((args.reference_dir / filename).read_bytes()).hexdigest()
            == float_report[key]
        )
    dataset = np.load(args.data_dir / "dataset.npz", allow_pickle=False)
    inputs = dataset["inputs"]
    assert hashlib.sha256(inputs.tobytes()).hexdigest() == float_report["inputs_sha256"]
    model, epsilon_changes = load_reference_model(args.model, args.reference_dir)
    if len(spec["input_shape"]) == 3:
        model = NHWCInput(model).eval()
    example = (torch.from_numpy(inputs[:1]),)
    captured = torch.export.export(model, example, strict=True).module()
    prepared = prepare_pt2e(captured, CortexMQuantizer(use_explicit_layout=True))
    calibration = (
        np.load(args.calibration_file, mmap_mode="r")
        if args.calibration_file
        else inputs[dataset["calibration_indices"]]
    )
    assert args.calibration_batch_size > 0
    assert calibration.dtype == np.float32 and calibration.shape[1:] == inputs.shape[1:]
    with torch.no_grad():
        for start in range(0, len(calibration), args.calibration_batch_size):
            prepared(
                torch.from_numpy(
                    calibration[start : start + args.calibration_batch_size].copy()
                )
            )
            if start % (100 * args.calibration_batch_size) == 0:
                print(
                    f"Calibrated {min(start + args.calibration_batch_size, len(calibration))}/{len(calibration)}",
                    flush=True,
                )
    converted = convert_pt2e(prepared)
    edge = to_edge_transform_and_lower(
        torch.export.export(converted, example, strict=True),
        compile_config=cortex_m_edge_compile_config(),
    )
    qi, qo = QuantizeInputs(edge, [0], method_name="forward"), QuantizeOutputs(
        edge, [0], method_name="forward"
    )
    edge = edge.transform([qi, qo])
    input_info, output_info = quantization_info(qi.quant_args[0]), quantization_info(
        qo.dequant_args[0]
    )
    assert input_info["dtype"] == output_info["dtype"] == "int8"
    if spec["softmax"]:
        assert output_info["scale"] == 1 / 256 and output_info["zero_point"] == -128
    reference_program = deepcopy(edge.exported_program())
    target = CortexMTargetConfig.from_target_string("cortex-m55")
    edge._edge_programs["forward"] = CortexMPassManager(
        edge.exported_program(), target_config=target, use_explicit_layout=True
    ).transform()
    lowered = edge.exported_program()
    lowered.validate()
    (out / "quantized_edge.graph.txt").write_text(str(reference_program.graph) + "\n")
    (out / f"{args.model}.graph.txt").write_text(str(lowered.graph) + "\n")
    integer_inputs = torch.ops.quantized_decomposed.quantize_per_tensor.default(
        torch.from_numpy(inputs), *qi.quant_args[0]
    ).contiguous()
    np.save(out / "inputs.npy", integer_inputs.numpy())
    implementations = {
        "quantized_edge": reference_program.module(check_guards=False),
        "cortex_m_python": lowered.module(check_guards=False),
    }
    if spec["softmax"]:
        implementations["cmsis_pool_reference"] = IntegerGlobalPoolReference(
            lowered.module(check_guards=False)
        ).run
    scores = {}
    for name, implementation in implementations.items():
        outputs = np.empty((len(inputs), spec["output_size"]), dtype=np.int8)
        with torch.no_grad():
            for index in range(len(inputs)):
                value = implementation(integer_inputs[index : index + 1])
                if isinstance(value, (list, tuple)):
                    value = value[0]
                assert value.dtype == torch.int8 and value.shape == (
                    1,
                    spec["output_size"],
                )
                outputs[index] = value.numpy()[0]
                if (index + 1) % 1000 == 0:
                    print(f"{name}: {index+1}/{len(inputs)}", flush=True)
        np.save(out / f"{name}.outputs.npy", outputs)
        scores[name] = quality(
            outputs, dataset, None if spec["softmax"] else output_info
        )
        print(name, scores[name], flush=True)
    pte = edge.to_executorch().buffer
    (out / f"{args.model}.pte").write_bytes(pte)
    program = deserialize_pte_binary(pte).program
    plan = next(plan for plan in program.execution_plan if plan.name == "forward")
    assert not plan.delegates
    for indices in (plan.inputs, plan.outputs):
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
    input_info.update(
        shape=plan.values[plan.inputs[0]].val.sizes,
        layout="NHWC" if len(spec["input_shape"]) == 3 else "NC",
    )
    output_info.update(shape=plan.values[plan.outputs[0]].val.sizes)
    source_patch = subprocess.check_output(["git", "diff", "--binary", "HEAD", "--"])
    (out / "source.patch").write_bytes(source_patch)
    cmsis = importlib.metadata.distribution("cmsis-nn")
    manifest = {
        "model": args.model,
        "source_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip(),
        "source_patch_sha256": hashlib.sha256(source_patch).hexdigest(),
        "source_weights_sha256": float_report["source_weights_sha256"],
        "source_config_sha256": float_report["source_config_sha256"],
        "torch": torch.__version__,
        "torchao": importlib.metadata.version("torchao"),
        "cmsis_nn_source": json.loads(cmsis.read_text("direct_url.json")),
        "target": "cortex-m55",
        "explicit_layout": True,
        "passes": [p.__name__ for p in CortexMPassManager.explicit_layout_pass_list],
        "batchnorm_epsilon": epsilon_changes,
        "calibration_samples": len(calibration),
        "calibration_inputs_sha256": hashlib.sha256(calibration).hexdigest(),
        "calibration_batch_size": args.calibration_batch_size,
        "inputs_sha256": hashlib.sha256(inputs.tobytes()).hexdigest(),
        "pte": f"{args.model}.pte",
        "bytes": len(pte),
        "sha256": hashlib.sha256(pte).hexdigest(),
        "input": input_info,
        "output": output_info,
        "runtime_operator_counts": dict(calls),
        "planned_nonconstant_buffer_sizes": plan.non_const_buffer_sizes,
        "quality": scores,
        "cmsis_pool_reference_scope": (
            "Diagnostic Python interpreter with global-pool integer rounding; exported program and runtime are unchanged"
            if spec["softmax"]
            else None
        ),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Exported {args.model}: {len(pte)} bytes; {dict(calls)}", flush=True)


if __name__ == "__main__":
    main()
