#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates
# <open-source-office@arm.com>
# SPDX-License-Identifier: Apache-2.0
"""Build, validate, and package four CPU-only E8 TFLM Tiny benchmark images."""

import argparse
import csv
import hashlib
import json
import os
import shutil
import subprocess
import tarfile
import urllib.request
from pathlib import Path

from tiny_build_profiles import (
    audit_flags, audit_int8_registrations, package_profile_docs,
    prepare_bundle, profile_manifest, profile_options,
    record_pair, tflm_attribution,
)


def sha256(path: Path) -> str:
    """Return the SHA256 of a file.

    :param path:    Input file.
    :returns:       Hexadecimal digest.
    """
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command: list[str], cwd: Path, env: dict[str, str], log: Path):
    """Run one build step, retaining combined output.

    :param command: Executable and arguments.
    :param cwd:     Working directory.
    :param env:     Process environment.
    :param log:     Output log path.
    """
    with log.open("w", encoding="utf-8") as stream:
        subprocess.run(
            command, cwd=cwd, env=env, stdout=stream, stderr=subprocess.STDOUT, check=True
        )


def build_identity(root: Path, gcc_bin: Path) -> dict:
    """Record the compiler version and repository base revision.

    :param root:    Repository root.
    :param gcc_bin: Cross-compiler executable directory.
    :returns:       Build identity fields.
    """
    return {
        "compiler": subprocess.check_output(
            [str(gcc_bin / "arm-none-eabi-gcc"), "-dumpfullversion"], text=True
        ).strip(),
        "repository_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True
        ).strip(),
    }


def configure_build(build: Path, options: list[str], env: dict[str, str], log: Path):
    """Configure a build directory immediately below the repository root.

    :param build:   Build directory.
    :param options: CMake configuration arguments.
    :param env:     Build environment.
    :param log:     Configure log.
    """
    run(["cmake", "-S", str(build.parent), "-B", str(build), *options], build.parent, env, log)


def compile_build(build: Path, targets: list[str], jobs: int, env: dict[str, str], log: Path):
    """Compile explicit targets and retain the full output.

    :param build:   Configured build directory.
    :param targets: Targets required for this image or validation.
    :param jobs:    Parallel compiler processes.
    :param env:     Build environment.
    :param log:     Build log.
    """
    run(
        ["cmake", "--build", str(build), "--target", *targets, "-j", str(jobs)],
        build.parent,
        env,
        log,
    )


def prepare_models(root: Path, source: dict) -> Path:
    """Fetch pinned model bytes and verify hashes, reusing existing downloads.

    :param root:    Repository root.
    :param source:  Pinned model manifest.
    :returns:       Model directory.
    """
    directory = root / "resources_downloaded/tflm_tiny"
    directory.mkdir(parents=True, exist_ok=True)
    base = f"https://raw.githubusercontent.com/mlcommons/tiny/{source['revision']}/"
    for model in source["models"].values():
        path = directory / model["filename"]
        if not path.exists():
            with urllib.request.urlopen(base + model["source_path"], timeout=60) as response:
                path.write_bytes(response.read())
        if sha256(path) != model["sha256"]:
            raise ValueError(f"Model hash mismatch: {path}")
    for filename, source_path in (
        ("LICENSE.mlcommons.md", "LICENSE.md"),
        ("LICENSE.anomaly_detection", "benchmark/training/anomaly_detection/LICENSE"),
    ):
        license_path = directory / filename
        if not license_path.exists():
            with urllib.request.urlopen(base + source_path, timeout=30) as response:
                license_path.write_bytes(response.read())
    return directory


def configure_args(root: Path, platform: str, model_id: str, model_path: Path) -> list[str]:
    """Construct the shared benchmark settings and platform-specific build flags.

    :param root:        Repository root.
    :param platform:    Native or E8 platform label.
    :param model_id:    Model identity for UART records.
    :param model_path:  Pinned TFLite file.
    :returns:           CMake arguments.
    """
    options = [
        "-G",
        "Ninja",
        "-DML_FRAMEWORK=TensorFlowLiteMicro",
        "-DUSE_CASE_BUILD=inference_runner",
        "-DETHOS_U_NPU_ENABLED=OFF",
        "-DMLEK_TFLM_SELECTIVE_BUILD=ON",
        "-DMLEK_TFLM_SELECT_INT8_OPS:BOOL=ON",
        "-DMLEK_LOG_ENABLE=ON",
        "-DHAL_LOG_ENABLE=ON",
        "-Dinference_runner_BENCHMARK_ENABLED=ON",
        "-Dinference_runner_WARMUP_COUNT=10",
        "-Dinference_runner_ITERATION_COUNT=100",
        "-Dinference_runner_TFLM_MEMORY_AUDIT=ON",
        "-Dinference_runner_ACTIVATION_BUF_SZ=0x40000",
        f"-Dinference_runner_MODEL_ID={model_id}",
        f"-Dinference_runner_MODEL_PATH={model_path}",
    ]
    if platform == "native":
        return options + ["-DTARGET_PLATFORM=native"]
    return options + [
        "-DTARGET_PLATFORM=alif",
        "-DTARGET_BOARD=DevKit-e8",
        "-DTARGET_SUBSYSTEM=RTSS-HP",
        "-DLINKER_SCRIPT_NAME=RTSS-HP-infrun",
        f"-DCMAKE_TOOLCHAIN_FILE={root}/scripts/cmake/toolchains/bare-metal-gcc.cmake",
        "-DCMAKE_BUILD_TYPE=Release",
        "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON",
        "-DCMAKE_C_FLAGS_RELEASE=-O3 -g -DNDEBUG",
        "-DCMAKE_CXX_FLAGS_RELEASE=-O3 -g -DNDEBUG",
        "-DGLCD_UI=OFF",
        "-DALIF_CAMERA_ENABLED=OFF",
        "-DALIF_ISP_ENABLED=ON",
        "-DCPU_PROFILE_ENABLED=ON",
        "-DCONSOLE_UART=4",
        "-DCMSIS_DSP_MIN_REQ_SRC_LIST=ON",
    ]


def snapshot_model(
    build: Path, dest: Path, model_path: Path, gcc_bin: Path, logging: bool = True
) -> dict:
    """Copy firmware, selection metadata, and exact flash/section accounting.

    :param build:       Embedded build directory.
    :param dest:        New per-model bundle directory.
    :param model_path:  Model file embedded in this image.
    :param gcc_bin:     GCC toolchain executables.
    :param logging:     Whether the image must contain UART memory reporting.
    :returns:           Flash and artifact identity metadata.
    """
    dest.mkdir()
    for name in ("mlek_inference_runner.axf", "mlek_inference_runner.map"):
        shutil.copy2(build / "bin" / name, dest / name)
    shutil.copy2(build / "bin/sectors/inference_runner/mram.bin", dest / "mram.bin")
    shutil.copy2(build / "CMakeCache.txt", dest / "CMakeCache.txt")
    shutil.copy2(model_path, dest / model_path.name)
    if model_path.suffix == ".tflite":
        for name in ("SelectedTflmModel.hpp", "selected_tflm_operators.json"):
            shutil.copy2(build / "generated/inference_runner/include" / name, dest / name)
    else:
        selection = build / "mlek-app/inference_runner_portable_ops_lib"
        shutil.copytree(selection, dest / "selection")
    elf = dest / "mlek_inference_runner.axf"
    sections = subprocess.check_output(
        [str(gcc_bin / "arm-none-eabi-size"), "-A", str(elf)], text=True
    )
    (dest / "sections.txt").write_text(sections, encoding="utf-8")
    symbols = subprocess.check_output(
        [str(gcc_bin / "arm-none-eabi-nm"), "-S", "-C", str(elf)], text=True
    )
    (dest / "symbols.txt").write_text(symbols, encoding="utf-8")
    payload = (dest / "mram.bin").read_bytes()
    marker = b"MEMORY et_total" if model_path.suffix == ".pte" else b"MEMORY total"
    if model_path.read_bytes() not in payload or (marker in payload) != logging:
        raise ValueError("Missing model or unexpected memory logging state in linked firmware")
    memory = {}
    for line in sections.splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[0].startswith("."):
            memory[parts[0]] = {"bytes": int(parts[1]), "address": hex(int(parts[2]))}
    (dest / "sections.json").write_text(json.dumps(memory, indent=2) + "\n", encoding="utf-8")
    return {
        "flash_total_bytes": len(payload),
        "flash_model_bytes": model_path.stat().st_size,
        "flash_non_model_bytes": len(payload) - model_path.stat().st_size,
        "firmware_sha256": sha256(dest / "mram.bin"),
        "elf_sha256": sha256(elf),
        "arena_reserved_bytes": 262144,
        "hardware_validated": False,
    }


def package(root: Path, bundle: Path, manifest: dict):
    """Add host scripts, reproducibility metadata, checksums, and a verified tar archive.

    :param root:        Repository root.
    :param bundle:      Prepared firmware bundle.
    :param manifest:    Final build manifest.
    """
    scripts = root / "scripts/py"
    shutil.copy2(scripts / "tflm_tiny_board.py", bundle / "run.py")
    (bundle / "run.py").chmod(0o755)
    shutil.copy2(scripts / "tflm_tiny_results.py", bundle / "tflm_tiny_results.py")
    if manifest.get("framework") == "ExecuTorch":
        shutil.copy2(root / "docs/e8_et_tiny.md", bundle / "README.md")
    else:
        shutil.copy2(root / "resources_downloaded/tflm_tiny/LICENSE.mlcommons.md", bundle)
        shutil.copy2(root / "resources_downloaded/tflm_tiny/LICENSE.anomaly_detection", bundle)
        shutil.copy2(root / "docs/e8_tflm_tiny.md", bundle / "README.md")
    if "profiles" in manifest:
        package_profile_docs(root, bundle, manifest)
    (bundle / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    with (bundle / "flash.csv").open("w", newline="", encoding="utf-8") as stream:
        columns = ["model"] + [
            key for key in next(iter(manifest["models"].values())) if key.startswith("flash_")
        ]
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows({"model": key, **value} for key, value in manifest["models"].items())
    (bundle / "source-changes.patch").write_bytes(
        subprocess.check_output(["git", "diff", "--binary"], cwd=root)
    )
    for name in (
        subprocess.check_output(
            ["git", "ls-files", "--others", "--exclude-standard", "-z"], cwd=root
        )
        .decode()
        .split("\0")
    ):
        if name:
            target = bundle / "new-source-files" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(root / name, target)
    files = sorted(path for path in bundle.rglob("*") if path.is_file())
    (bundle / "SHA256SUMS").write_text(
        "".join(f"{sha256(path)}  {path.relative_to(bundle)}\n" for path in files), encoding="utf-8"
    )
    archive = root / "build-artifacts" / f"{bundle.name}.tar.gz"
    if archive.exists():
        raise FileExistsError(f"Refusing to overwrite {archive}")
    with tarfile.open(archive, "w:gz") as stream:
        stream.add(bundle, arcname=bundle.name)
    Path(str(archive) + ".sha256").write_text(
        f"{sha256(archive)}  {archive.name}\n", encoding="utf-8"
    )
    with tarfile.open(archive) as stream:
        for path in files:
            content = stream.extractfile(f"{bundle.name}/{path.relative_to(bundle)}")
            if content is None or hashlib.sha256(content.read()).hexdigest() != sha256(path):
                raise ValueError(f"Archive verification failed: {path}")
    print(f"Verified {archive} ({archive.stat().st_size} bytes)", flush=True)


def build_e8_pair(
    bundle: Path, args: argparse.Namespace, model_id: str, model: dict, env: dict[str, str]
) -> dict:
    """Build silent and logged images with identical optimization and memory settings.

    :param bundle:      New artifact directory.
    :param args:        Compiler and concurrency settings.
    :param model_id:    Short benchmark model ID.
    :param model:       Pinned TFLite model metadata.
    :param env:         Build environment.
    :returns:           Logging-on metadata with a separate size-build record.
    """
    root = bundle.parent
    model_path = root / "resources_downloaded/tflm_tiny" / model["filename"]
    pair = {}
    for profile in ("size", "latency"):
        logging = profile == "latency"
        print(f"Building e8 {model_id} {profile}", flush=True)
        build = root / f"build-e8-tflm-tiny-oz-{profile}"
        prefix = bundle / "validation" / f"e8-{model_id}-{profile}"
        configure_build(
            build, configure_args(root, "e8", model_id, model_path)
            + profile_options(logging, f"{bundle.name}-{profile}"),
            env, Path(str(prefix) + "-configure.log"),
        )
        compile_build(build, ["mlek_inference_runner"], args.jobs, env,
                      Path(str(prefix) + "-build.log"))
        folder = (bundle if logging else bundle / "size") / model_id
        metadata = dict(model, **snapshot_model(build, folder, model_path, args.gcc_bin, logging))
        metadata["compiler_audit"] = audit_flags(build, folder, logging)
        metadata.update(audit_int8_registrations(folder))
        metadata.update(tflm_attribution(build, folder, metadata))
        pair[profile] = metadata
    record_pair(bundle, model_id, pair["latency"], pair["size"])
    return pair["latency"]


def main():
    """Build each model using shared native/embedded build trees and freeze their outputs."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gcc-bin", type=Path, required=True)
    parser.add_argument("--jobs", type=int, default=8)
    parser.add_argument("--bundle-name", default="build-e8-tflm-tiny-artifacts")
    parser.add_argument("--no-package", action="store_true", help="Leave a build for final review")
    parser.add_argument("--paired-profiles", action="store_true",
                        help="Oz runtime/O3 CMSIS: silent size images plus logged latency images")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    source = json.loads((root / "scripts/py/tflm_tiny_models.json").read_text(encoding="utf-8"))
    models = prepare_models(root, source)
    bundle = prepare_bundle(root, args)
    logs = bundle / "validation"
    env = dict(os.environ)
    env["PATH"] = f"{root}/resources_downloaded/env/bin:{args.gcc_bin}:{env['PATH']}"
    manifest = {
        "source": source,
        "benchmark": {"warmups": 10, "measurements": 100},
        "board": "DevKit-e8",
        "core": "M55-HP",
        "npu": False,
        "tflm_int8_selection": True,
        **build_identity(root, args.gcc_bin),
        "dependencies": {},
        "models": {},
    }
    manifest["dependencies"] = {
        name: subprocess.check_output(
            ["git", "-C", str(root / "dependencies" / name), "rev-parse", "HEAD"], text=True
        ).strip()
        for name in ("tensorflow", "cmsis-nn", "cmsis-alif")
    }
    manifest.update(profile_manifest(bundle, args.paired_profiles))
    for model_id in ("kws", "ic", "vww", "ad"):
        model = source["models"][model_id]
        model_path = models / model["filename"]
        for platform in ("native", "e8"):
            if platform == "e8" and args.paired_profiles:
                manifest["models"][model_id] = build_e8_pair(bundle, args, model_id, model, env)
                (bundle / "manifest.json").write_text(
                    json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
                )
                continue
            print(f"Building {platform} {model_id}", flush=True)
            build = root / f"build-{platform}-tflm-tiny"
            prefix = logs / f"{platform}-{model_id}"
            configure_build(
                build,
                configure_args(root, platform, model_id, model_path),
                env,
                Path(str(prefix) + "-configure.log"),
            )
            compile_build(
                build,
                ["mlek_inference_runner"]
                + (["inference_runner_tests"] if platform == "native" else []),
                args.jobs,
                env,
                Path(str(prefix) + "-build.log"),
            )
            if platform == "native":
                run(
                    ["ctest", "--test-dir", str(build), "--output-on-failure"],
                    root,
                    env,
                    Path(str(prefix) + "-tests.log"),
                )
                run(
                    [str(build / "bin/mlek_inference_runner")],
                    root,
                    env,
                    Path(str(prefix) + "-runner.log"),
                )
            else:
                manifest["models"][model_id] = dict(
                    model, **snapshot_model(build, bundle / model_id, model_path, args.gcc_bin)
                )
    (bundle / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    if not args.no_package:
        package(root, bundle, manifest)


if __name__ == "__main__":
    main()
