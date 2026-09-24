#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates
# <open-source-office@arm.com>
# SPDX-License-Identifier: Apache-2.0
"""Build four E8 ExecuTorch images from the frozen Cortex-M55 int8 export bundle."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess

import numpy as np

from build_tflm_tiny import (
    build_identity,
    configure_args,
    configure_build,
    compile_build,
    package,
    sha256,
    snapshot_model,
)
from et_tiny_flash import analyze_model
from tiny_inference_memory import audit_memory
from tiny_build_profiles import (
    audit_flags, prepare_bundle, profile_manifest, profile_options, record_pair,
)

MODELS = {"kws": "ds_cnn", "ic": "resnet8", "vww": "mobilenet_v1_025", "ad": "deep_autoencoder"}
SOURCE_TREE = "0510beb4b48b8785477a3c11b23c5bc18bd7841a"


def validation_header(export: Path, name: str, output: Path) -> dict:
    """Embed saved int8 input/output pairs for untimed on-board validation.

    :param export:  Frozen exporter directory.
    :param name:    Exporter's model name.
    :param output:  Generated header destination.
    :returns:       Fixture byte count, sample count and reference identity.
    """
    source = [
        "// SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates",
        "// <open-source-office@arm.com>",
        "// SPDX-License-Identifier: Apache-2.0",
        "#pragma once",
        "#include <cstdint>",
        "namespace arm::app::inference_runner {",
    ]
    reference = json.loads((export / "manifest.json").read_text(encoding="utf-8")).get(
        "validation_reference", "lowered_python_int8"
    )
    if reference not in ("lowered_python_int8", "cortex_m_native_int8"):
        raise ValueError(f"Unsupported validation reference: {reference}")
    source.insert(5, f'#define INFERENCE_VALIDATION_REFERENCE "{reference}"')
    total = 0
    counts = []
    for kind in ("inputs", "outputs"):
        data = np.load(export / f"{name}.validation_{kind}.npy", allow_pickle=False)
        if data.dtype != np.int8 or data.ndim < 2 or data.shape[0] < 1:
            raise ValueError(f"Expected nonempty int8 validation {kind} for {name}")
        counts.append(data.shape[0])
        data = data.reshape(data.shape[0], -1)
        total += data.nbytes
        source.append(
            f"alignas(16) const int8_t kValidation{kind.title()}[{data.shape[0]}]"
            f"[{data.shape[1]}] = {{"
        )
        for sample in data:
            source.append("{")
            for start in range(0, len(sample), 16):
                source.append(",".join(str(value) for value in sample[start : start + 16]) + ",")
            source.append("},")
        source.append("};")
    source.append("}")
    if counts[0] != counts[1]:
        raise ValueError(f"Input/output validation counts differ for {name}")
    output.write_text("\n".join(source) + "\n", encoding="utf-8")
    return {"validation_fixture_bytes": total, "validation_samples": counts[0],
            "validation_reference": reference}


def et_options(root: Path, model_id: str, model_path: Path, header: Path) -> list[str]:
    """Use the TFLM board settings with the matching ET runtime and reporting enabled.

    :param root:        Repository root.
    :param model_id:    UART model ID.
    :param model_path:  Frozen PTE.
    :param header:      Generated validation fixtures.
    :returns:           CMake configure options.
    """
    options = configure_args(root, "e8", model_id, model_path)
    options = [arg for arg in options if "TFLM" not in arg and "ML_FRAMEWORK=" not in arg]
    return options + [
        "-DML_FRAMEWORK=ExecuTorch",
        f"-DEXECUTORCH_SRC_PATH={root}/resources_downloaded/et_tiny/executorch",
        "-DMLEK_EXECUTORCH_SELECTIVE_BUILD=ON",
        "-DMLEK_EXECUTORCH_SELECT_PRIM_OPS=ON",
        "-DCORTEX_M_ENABLE_RUNTIME_CHECKS=ON",
        "-DML_FWK_TMP_MEM_SIZE=65536",
        "-Dinference_runner_ET_MEMORY_REPORT=ON",
        f"-Dinference_runner_VALIDATION_HEADER:STRING={header}",
    ]


def compile_model(
    bundle: Path, args: argparse.Namespace, model_id: str, model_path: Path, logging: bool
) -> tuple[Path, dict]:
    """Compile one profile with the frozen export's validation fixtures.

    :param bundle:      New output bundle directory.
    :param args:        Toolchain and build concurrency options.
    :param model_id:    Short benchmark model ID.
    :param model_path:  Frozen PTE file.
    :param logging:     Whether this is the UART-capable latency image.
    :returns:           Build directory and validation fixture metadata.
    """
    root = bundle.parent
    header = bundle / "validation" / f"{model_id}-validation.hpp"
    validation = validation_header(model_path.parent, model_path.stem, header)
    profile = "latency" if logging else "size"
    build = root / (
        f"build-e8-et-tiny-oz-{profile}" if args.paired_profiles else "build-e8-et-tiny"
    )
    options = et_options(root, model_id, model_path, header)
    if args.paired_profiles:
        options += profile_options(logging, f"{bundle.name}-{profile}", "ExecuTorch")
    prefix = header.with_name(f"{model_id}-{profile}")
    env = dict(os.environ)
    env["PATH"] = f"{root}/resources_downloaded/env/bin:{args.gcc_bin}:{env['PATH']}"
    print(f"Building {model_id}: {model_path.stem} {profile}", flush=True)
    configure_build(
        build,
        options,
        env,
        prefix.with_suffix(".configure.log"),
    )
    compile_build(
        build, ["mlek_inference_runner"], args.jobs, env, prefix.with_suffix(".build.log")
    )
    return build, validation


def build_model(
    bundle: Path, args: argparse.Namespace, model_id: str, model: dict, logging: bool = True
) -> dict:
    """Build and snapshot one model's firmware, selection, fixtures, and accounting.

    :param bundle:      New output bundle directory.
    :param args:        Toolchain and build concurrency options.
    :param model_id:    Short benchmark model ID.
    :param model:       Exporter's model metadata.
    :param logging:     Whether this is the UART-capable latency image.
    :returns:           Completed per-model manifest entry.
    """
    model_path = bundle / "export" / model["pte"]
    build, validation = compile_model(bundle, args, model_id, model_path, logging)
    folder = (bundle if logging else bundle / "size") / model_id
    metadata = dict(model, **snapshot_model(build, folder, model_path, args.gcc_bin, logging))
    metadata["inference_memory"] = audit_memory(folder, args.gcc_bin, True)
    if args.paired_profiles:
        metadata["compiler_audit"] = audit_flags(build, folder, logging)
    metadata.update(
        planned_bytes=sum(model["planned_nonconstant_buffer_sizes"]),
        temp_reserved_bytes=65536,
        **validation,
        heap_measurement_scope="inference_batch_v1",
        input_storage="method_owned",
        input_pool_allocation_bytes=0,
    )
    metadata.update(analyze_model(folder, metadata))
    return metadata


def main():
    """Build, account, and optionally freeze all four images without changing PTEs."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gcc-bin", type=Path, required=True)
    parser.add_argument("--jobs", type=int, default=8)
    parser.add_argument("--bundle-name", default="build-e8-et-tiny-artifacts")
    parser.add_argument("--no-package", action="store_true")
    parser.add_argument(
        "--export-dir", type=Path,
        help="Verified normalized export directory; defaults to the original export",
    )
    parser.add_argument("--paired-profiles", action="store_true",
                        help="Oz runtime/O3 CMSIS: silent size images plus logged latency images")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    export = (args.export_dir or root / "resources_downloaded/et_tiny/mlperf-tiny-cortex-m55-int8"
              ).resolve()
    source = root / "resources_downloaded/et_tiny/executorch"
    for line in (export / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        digest, name = line.split("  ", 1)
        if sha256(export / name) != digest:
            raise ValueError(f"Export checksum mismatch: {name}")
    if subprocess.check_output(["git", "write-tree"], cwd=source, text=True).strip() != SOURCE_TREE:
        raise ValueError("Stage the export patch in the isolated ET checkout to verify its tree")
    subprocess.run(["git", "diff", "--exit-code"], cwd=source, check=True)
    exported = json.loads((export / "manifest.json").read_text(encoding="utf-8"))
    bundle = prepare_bundle(root, args)
    shutil.copytree(export, bundle / "export")
    shutil.copy2(source / "LICENSE", bundle / "LICENSE.executorch")
    manifest = {
        "framework": "ExecuTorch",
        "source": exported,
        "executorch_tree": SOURCE_TREE,
        "export_zip_sha256": (exported.get("source_archive_sha256") or
                              sha256(export.with_suffix(".zip"))),
        "benchmark": {"warmups": 10, "measurements": 100},
        "board": "DevKit-e8",
        "core": "M55-HP",
        "npu": False,
        "runtime_checks": True,
        "inference_memory": "sram",
        **build_identity(root, args.gcc_bin),
        "dependencies": {
            name: subprocess.check_output(
                ["git", "-C", str(root / "dependencies" / name), "rev-parse", "HEAD"], text=True
            ).strip()
            for name in ("cmsis-nn", "cmsis-alif")
        },
        "models": {},
    }
    manifest.update(profile_manifest(bundle, args.paired_profiles))
    for model_id, name in MODELS.items():
        if args.paired_profiles:
            size = build_model(bundle, args, model_id, exported["models"][name], logging=False)
        manifest["models"][model_id] = build_model(
            bundle, args, model_id, exported["models"][name]
        )
        if args.paired_profiles:
            record_pair(bundle, model_id, manifest["models"][model_id], size)
        (bundle / "manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
    if not args.no_package:
        package(root, bundle, manifest)


if __name__ == "__main__":
    main()
