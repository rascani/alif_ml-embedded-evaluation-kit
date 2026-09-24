#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates
# <open-source-office@arm.com>
# SPDX-License-Identifier: Apache-2.0
"""Validate E8 inference archives on Corstone-300; simulator timings are not E8 results."""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess

from build_tflm_tiny import compile_build, configure_build, run, sha256
from tflm_tiny_results import parse_boot
from tflm_int8_probe import compare_int8


def startup_objects(root: Path, gcc: Path, output: Path, env: dict[str, str]) -> list[str]:
    """Build the CMSIS Corstone startup separately from the E8 runtime libraries.

    :param root:    Repository root.
    :param gcc:     Cross-toolchain executable directory.
    :param output:  Probe files and logs.
    :param env:     Build environment.
    :returns:       Startup and system object paths.
    """
    device = root / "dependencies/cortex-dfp/Device/ARMCM55"
    objects = []
    for name in ("startup_ARMCM55", "system_ARMCM55"):
        obj = output / f"{name}.o"
        run([
            str(gcc / "arm-none-eabi-gcc"), "-Oz", "-g", "-mcpu=cortex-m55", "-mthumb",
            "-mfloat-abi=hard", "-DARMCM55", "-ffunction-sections", "-fdata-sections",
            "-I", str(device / "Include"),
            "-I", str(root / "dependencies/cmsis-6/CMSIS/Core/Include"),
            "-c", str(device / "Source" / f"{name}.c"), "-o", str(obj),
        ], root, env, output / f"{name}.log")
        objects.append(str(obj))
    return objects


def link_command(args: argparse.Namespace, framework: str, objects: list[str]) -> list[str]:
    """Link the actual E8 inference libraries with a semihosting startup and timer.

    :param args:        Probe build paths and toolchain.
    :param framework:   ExecuTorch or TensorFlowLiteMicro.
    :param objects:     CMSIS startup objects.
    :returns:           Link command, without its output argument.
    """
    root = Path(__file__).resolve().parents[2]
    harness = root / "tests/integration/tiny_fvp"
    command = [
        str(args.gcc_bin / "arm-none-eabi-g++"), "-Oz", "-g", "-DNDEBUG",
        "-mcpu=cortex-m55", "-mthumb", "-mfloat-abi=hard", "--specs=rdimon.specs",
        "-Wl,--nmagic,--gc-sections", "-T", str(harness / "runner.ld"),
        "--entry", "Reset_Handler", "-I",
        str(root / "source/hal/source/components/platform_pmu/include"),
        str(harness / "main.cpp"), *objects,
    ]
    libraries = ["inference_runner", "profiler", "cmsis-nn"]
    if framework == "ExecuTorch":
        command += [str(args.build / "mlek-app/CMakeFiles/mlek_inference_runner.dir/"
                        "__/lib/mlek/fwk/executorch/EtPal.cc.obj")]
        command += ["-Wl,--start-group", "-Wl,--whole-archive"]
        command += [str(args.build / "lib" / f"lib{name}.a") for name in (
            "inference_runner_portable_ops_lib_portable",
            "inference_runner_portable_ops_lib_quantized",
            "inference_runner_portable_ops_lib_cortex_m", "executorch",
        )]
        command += ["-Wl,--no-whole-archive"]
        libraries += ["ml_framework_et", "extension_runner_util", "portable_kernels",
                      "quantized_kernels", "cortex_m_kernels", "kernels_util_all_deps",
                      "executorch_core"]
    else:
        command += ["-Wl,--start-group"]
        libraries += ["ml_framework_tflm", "tflu"]
    return command + [str(args.build / "lib" / f"lib{name}.a") for name in libraries] + [
        "-Wl,--end-group"
    ]


def validate_model(
    args: argparse.Namespace, manifest: dict, model_id: str, command: list[str]
) -> dict:
    """Rebuild a frozen profile, require identical MRAM bytes, then validate its FVP output.

    :param args:        Bundle, build tree, compiler and simulator paths.
    :param manifest:    Frozen image metadata.
    :param model_id:    Model to validate.
    :param command:     Probe linker command.
    :returns:           Validation status and memory records, excluding simulator latency.
    """
    root = Path(__file__).resolve().parents[2]
    env = dict(os.environ)
    env["PATH"] = f"{root}/resources_downloaded/env/bin:{args.gcc_bin}:{env['PATH']}"
    output = args.bundle / "validation/fvp"
    cache = (args.bundle / model_id / "CMakeCache.txt").read_text(encoding="utf-8")
    options = ["-D" + line for line in cache.splitlines() if any(
        line.startswith(f"inference_runner_{key}:")
        for key in ("MODEL_ID", "MODEL_PATH", "BUILD_ID", "VALIDATION_HEADER")
    )]
    if manifest.get("framework") != "ExecuTorch":
        selection = re.search(r"^MLEK_TFLM_SELECT_INT8_OPS:[^=]+=(?:ON|TRUE|1)$",
                              cache, re.MULTILINE) is not None
        options.append(f"-DMLEK_TFLM_SELECT_INT8_OPS={'ON' if selection else 'OFF'}")
    configure_build(args.build, options, env, output / f"{model_id}-configure.log")
    compile_build(args.build, ["mlek_inference_runner"], args.jobs, env,
                  output / f"{model_id}-build.log")
    firmware = args.build / "bin/sectors/inference_runner/mram.bin"
    if sha256(firmware) != manifest["models"][model_id]["firmware_sha256"]:
        raise ValueError(f"{model_id}: rebuilt E8 firmware differs from frozen image")
    elf = output / f"{model_id}.axf"
    run(command + ["-o", str(elf)], root, env, output / f"{model_id}-link.log")
    log = output / f"{model_id}.log"
    with log.open("w", encoding="utf-8") as stream:
        subprocess.run([
            str(args.fvp), "-C", "mps3_board.visualisation.disable-visualisation=1",
            "-C", "mps3_board.telnetterminal0.start_telnet=0",
            "-C", "cpu0.semihosting-enable=1", "-C", "cpu0.semihosting-stack_base=0",
            "-C", "cpu0.semihosting-heap_limit=0", "-a", str(elf), "--timelimit", "60",
        ], stdout=stream, stderr=subprocess.STDOUT, check=True, timeout=70)
    parsed = parse_boot(
        "INFO - Processor internal clock: 400000000Hz\n" + log.read_text(encoding="utf-8"),
        manifest, model_id,
    )
    return {
        "status": "PASS", "e8_firmware_sha256": sha256(firmware),
        "fvp_elf_sha256": sha256(elf), "log_sha256": sha256(log),
        "measured_invocations_checked": parsed["count"],
        "validation_samples": parsed.get("validation_samples", 0),
        "memory": {key: value for key, value in parsed.items() if key.startswith(
            ("ram_", "arena_", "et_", "runtime_static", "input_pool", "invoke_", "diagnostic_")
        )},
    }


def main():
    """Validate all four models before their bundle is packaged."""
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("bundle", "build", "gcc-bin", "fvp"):
        parser.add_argument(f"--{name}", type=lambda value: Path(value).resolve(), required=True)
    parser.add_argument("--jobs", type=int, default=8)
    parser.add_argument("--compare-int8", action="store_true",
                        help="Compare specialized and generic CMSIS-NN outputs in a separate probe")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    output = args.bundle / "validation/fvp"
    output.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((args.bundle / "manifest.json").read_text(encoding="utf-8"))
    objects = startup_objects(root, args.gcc_bin, output, dict(os.environ))
    command = link_command(args, manifest.get("framework", "TensorFlowLiteMicro"), objects)
    (output / "link-command.json").write_text(
        json.dumps(command, indent=2) + "\n", encoding="utf-8"
    )
    checks = {"scope": "Corstone functional validation only; not E8 latency/RAM", "models": {}}
    for model_id in manifest["models"]:
        checks["models"][model_id] = validate_model(args, manifest, model_id, command)
        if args.compare_int8:
            checks["models"][model_id]["int8_comparison"] = compare_int8(args, model_id, command)
        (output / "checks.json").write_text(json.dumps(checks, indent=2) + "\n", encoding="utf-8")
        print(f"{model_id}: FVP PASS; E8 MRAM byte-for-byte reproduced", flush=True)


if __name__ == "__main__":
    main()
