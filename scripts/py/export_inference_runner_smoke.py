#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates
# <open-source-office@arm.com>
# SPDX-License-Identifier: Apache-2.0
"""Export small deterministic ExecuTorch bring-up models, separate from MLPerf Tiny."""

import argparse
import json
from pathlib import Path

import torch
from executorch.backends.cortex_m.edge_compile_config import cortex_m_edge_compile_config
from executorch.backends.cortex_m.passes.cortex_m_pass_manager import CortexMPassManager
from executorch.backends.cortex_m.quantizer.quantizer import CortexMQuantizer
from executorch.exir import EdgeProgramManager, to_edge_transform_and_lower
from executorch.version import git_version
from torch.export import export
from torchao.quantization.pt2e.quantize_pt2e import convert_pt2e, prepare_pt2e


def export_smoke_models(output_dir: Path):
    """
    Export a Cortex-M quantized model and its portable floating-point counterpart.

    :param output_dir:  Destination for the programs and reference JSON.
    """
    torch.manual_seed(0)
    model = torch.nn.Sequential(
        torch.nn.Linear(16, 8), torch.nn.ReLU(), torch.nn.Linear(8, 4)
    ).eval()
    inputs = (torch.linspace(-1, 1, 16).reshape(1, 16),)
    # PyTorch 2.14 inserts a call_module guard by default, which PT2E cannot transform.
    prepared = prepare_pt2e(
        export(model, inputs).module(check_guards=False), CortexMQuantizer()
    )
    for sample in (inputs[0], torch.zeros(1, 16), torch.ones(1, 16), -torch.ones(1, 16)):
        prepared(sample)
    quantized = convert_pt2e(prepared)
    reference = quantized(*inputs).detach()
    edge = to_edge_transform_and_lower(
        export(quantized, inputs), compile_config=cortex_m_edge_compile_config()
    )
    edge = EdgeProgramManager(
        CortexMPassManager(edge.exported_program()).transform(),
        compile_config=cortex_m_edge_compile_config(),
    )
    cortex_program = edge.to_executorch()
    plan = cortex_program.executorch_program.execution_plan[0]
    operators = [f"{op.name}.{op.overload}" for op in plan.operators]
    if plan.delegates or "cortex_m::quantized_linear.out" not in operators:
        raise RuntimeError(f"Expected CPU-only Cortex-M linear kernels, got {operators}")

    portable_program = to_edge_transform_and_lower(export(model, inputs)).to_executorch()
    metadata = {
        "purpose": "Bring-up only; these are not MLPerf Tiny models",
        "executorch_commit": git_version,
        "torch_version": torch.__version__,
        "input": inputs[0].tolist(),
        "quantized_reference": reference.tolist(),
        "portable_reference": model(*inputs).detach().tolist(),
        "operators": operators,
        "planned_buffer_sizes": plan.non_const_buffer_sizes,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "smoke-cortex-m.pte").write_bytes(cortex_program.buffer)
    (output_dir / "smoke-portable.pte").write_bytes(portable_program.buffer)
    (output_dir / "smoke.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(f"Exported smoke models to {output_dir}: {operators}")


def main():
    """Parse the output directory and export both programs."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir", type=Path, default=Path("resources_downloaded/inference_runner")
    )
    export_smoke_models(parser.parse_args().output_dir)


if __name__ == "__main__":
    main()
