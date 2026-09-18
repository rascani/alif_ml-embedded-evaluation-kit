#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates
# <open-source-office@arm.com>
# SPDX-License-Identifier: Apache-2.0
"""Link an isolated E8 timer diagnostic while preserving existing benchmark builds."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tarfile

from alif_timer_results import parse_boot

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "tests/integration/alif_timer"


def digest(path: Path) -> str:
    """Calculate artifact identity.

    :param path:    Artifact file.
    :returns:       SHA256 digest.
    """
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command: list[str], build: Path, log: Path):
    """Record and execute one command without a shell.

    :param command: Command arguments.
    :param build:   Directory for original relative object paths.
    :param log:     Output log.
    """
    log.with_suffix(".command.json").write_text(json.dumps(command, indent=2) + "\n",
                                               encoding="utf-8")
    with log.open("w", encoding="utf-8") as stream:
        subprocess.run(command, cwd=build, stdout=stream, stderr=subprocess.STDOUT, check=True)


def compile_source(row: dict, source: Path, output: Path,
                   build_id: str, fvp: bool = False):
    """Reuse benchmark compilation flags for one diagnostic source file.

    :param row:         Original compilation database entry providing flags.
    :param source:      Source to compile.
    :param output:      New object path.
    :param build_id:    Unique UART identity.
    :param fvp:         Use standard CMSIS M55 device headers for simulation.
    """
    command = shlex.split(row["command"])
    command[command.index("-o") + 1] = str(output)
    command[command.index("-c") + 1] = str(source)
    command += [f'-DTIMER_VALIDATION_BUILD_ID="{build_id}"', "-I",
                str(ROOT / "source/hal/source/platform/alif/include")]
    if fvp:
        command[1:1] = ["-I", str(SOURCE / "fvp")]
    run(command, Path(row["directory"]), output.with_suffix(".compile.log"))


def e8_link(build: Path, output: Path, obj: Path) -> list[str]:
    """Extract only the existing linker invocation and redirect all outputs.

    :param build:   Existing Ninja build directory.
    :param output:  New bundle firmware directory.
    :param obj:     Diagnostic MainLoop object.
    :returns:       Link command with original platform objects and no inference runner.
    """
    commands = subprocess.check_output(
        ["ninja", "-C", str(build), "-t", "commands", "bin/mlek_inference_runner.axf"], text=True)
    line = next(line for line in commands.splitlines()
                if "-o bin/mlek_inference_runner.axf" in line)
    tokens = shlex.split(line)
    start = next(index for index, token in enumerate(tokens) if token.endswith("arm-none-eabi-g++"))
    command = tokens[start:tokens.index("&&", start)]
    command[command.index("-o") + 1] = str(output / "timer.axf")
    command = [f"-Map={output / 'timer.map'}" if token.startswith("-Map=") else token
               for token in command if not token.endswith("libinference_runner.a")]
    command.insert(1, str(obj))
    return command


def validate_fvp(args: argparse.Namespace, rows: list[dict], bundle: Path, manifest: dict):
    """Run the same diagnostic against the production SysTick implementation on M55.

    :param args:        Build and simulator arguments.
    :param rows:        Compilation database.
    :param bundle:      New artifact directory.
    :param manifest:    Firmware identity.
    """
    output = bundle / "validation"
    objects = []
    for original, source, name in (
        ("MainLoop.cc", SOURCE / "TimerValidation.cc", "validation.o"),
        ("MainLoop.cc", SOURCE / "FvpMain.cc", "main.o"),
        ("timer_alif.c", ROOT / "source/hal/source/platform/alif/source/timer_alif.c", "timer.o"),
        ("hal_pmu.c", ROOT / "source/hal/source/hal_pmu.c", "hal_pmu.o"),
    ):
        obj = output / name
        row = next(item for item in rows if Path(item["file"]).name == original)
        compile_source(row, source, obj, manifest["build_id"], True)
        objects.append(str(obj))
    # Reuse previously validated standard Corstone startup and linker layout.
    startup = ROOT / "build-e8-tflm-tiny-artifacts-v3/validation/fvp"
    command = [manifest["compiler_path"], "-Oz", "-g", "-mcpu=cortex-m55", "-mthumb",
               "-mfloat-abi=hard", "--specs=rdimon.specs", "-Wl,--nmagic,--gc-sections",
               "-T", str(ROOT / "tests/integration/tiny_fvp/runner.ld"), *objects,
               str(startup / "startup_ARMCM55.o"), str(startup / "system_ARMCM55.o"),
               "-o", str(output / "timer-fvp.axf")]
    run(command, args.base_build, output / "fvp-link.log")
    command = [str(args.fvp), "-C", "mps3_board.visualisation.disable-visualisation=1",
               "-C", "mps3_board.telnetterminal0.start_telnet=0", "-C", "cpu0.semihosting-enable=1",
               "-C", "cpu0.semihosting-stack_base=0", "-C", "cpu0.semihosting-heap_limit=0",
               "-a", str(output / "timer-fvp.axf"), "--timelimit", "300"]
    run(command, args.base_build, output / "fvp-run.log")
    report = parse_boot((output / "fvp-run.log").read_text(encoding="utf-8"), manifest)
    report["scope"] = "Corstone simulated-counter functional validation; physical E8 run pending"
    (output / "fvp-results.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def package_bundle(bundle: Path):
    """Include runnable Mac tools, documentation, source and checksum inventories.

    :param bundle:  Completed diagnostic directory.
    """
    for name in ("alif_timer_results.py", "tflm_tiny_board.py", "tflm_tiny_results.py"):
        shutil.copy2(ROOT / "scripts/py" / name, bundle / name)
    shutil.copy2(ROOT / "scripts/py/alif_timer_board.py", bundle / "run.py")
    shutil.copy2(ROOT / "docs/e8_timer_validation.md", bundle / "README.md")
    shutil.copytree(SOURCE, bundle / "source")
    files = sorted(path for path in bundle.rglob("*") if path.is_file())
    (bundle / "SHA256SUMS").write_text(
        "".join(f"{digest(path)}  {path.relative_to(bundle)}\n" for path in files),
        encoding="utf-8")
    archive = bundle.with_suffix(".tar.gz")
    with tarfile.open(archive, "x:gz") as stream:
        stream.add(bundle, arcname=bundle.name)
    archive.with_suffix(archive.suffix + ".sha256").write_text(
        f"{digest(archive)}  {archive.name}\n", encoding="utf-8")
    print(f"Created {archive}", flush=True)


def main():
    """Build and package a diagnostic without altering benchmark firmware or libraries."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-build", type=Path, default=ROOT / "build-e8-tflm-tiny-oz-latency")
    parser.add_argument("--bundle-name", default="build-e8-timer-validation-artifacts-v1")
    parser.add_argument("--fvp", type=Path)
    args = parser.parse_args()
    args.base_build = args.base_build.resolve()
    cache = (args.base_build / "CMakeCache.txt").read_text(encoding="utf-8")
    for name, value in (("TARGET_PLATFORM", "alif"), ("TARGET_BOARD", "DevKit-e8"),
                        ("TARGET_SUBSYSTEM", "RTSS-HP"), ("CPU_PROFILE_ENABLED", "ON"),
                        ("ETHOS_U_NPU_ENABLED", "OFF")):
        if not re.search(rf"^{name}:[^=]+={value}$", cache, re.MULTILINE):
            parser.error(f"--base-build requires {name}={value}")
    if not re.fullmatch(r"build-[A-Za-z0-9_-]+", args.bundle_name):
        parser.error("--bundle-name must be a new build-* directory name")
    bundle = ROOT / args.bundle_name
    bundle.mkdir()
    output = bundle / "timer"
    output.mkdir()
    (bundle / "validation").mkdir()
    rows = json.loads((args.base_build / "compile_commands.json").read_text(encoding="utf-8"))
    row = next(item for item in rows if Path(item["file"]).name == "MainLoop.cc")
    compile_source(row, SOURCE / "TimerValidation.cc", output / "timer.o", bundle.name)
    command = e8_link(args.base_build, output, output / "timer.o")
    inputs = {str(path.resolve()): digest(path) for token in command
              if (path := args.base_build / token).is_file() and path != output / "timer.o"}
    run(command, args.base_build, output / "link.log")
    compiler = next(token for token in command if token.endswith("arm-none-eabi-g++"))
    run([compiler.replace("g++", "objcopy"), "-O", "binary", "--only-section=*.at_mram",
         str(output / "timer.axf"), str(output / "mram.bin")],
        args.base_build, output / "objcopy.log")
    manifest = {
        "build_id": bundle.name, "board": "DevKit-e8", "core": "M55-HP", "clock_hz": 400000000,
        "npu": False, "scope": "Standalone timer validation; benchmark firmware unchanged",
        "compiler_path": compiler, "linked_input_sha256": inputs,
        "timer_source_sha256": digest(ROOT / "source/hal/source/platform/alif/source/timer_alif.c"),
        "diagnostic_source_sha256": digest(SOURCE / "TimerValidation.cc"),
        "models": {"timer": {"firmware_sha256": digest(output / "mram.bin"),
                              "flash_total_bytes": (output / "mram.bin").stat().st_size}},
        "hardware_validation": "pending",
    }
    if args.fvp:
        validate_fvp(args, rows, bundle, manifest)
        manifest["simulator_validation"] = "PASS"
    if any(digest(Path(path)) != value for path, value in inputs.items()):
        raise ValueError("An original linked input changed during diagnostic build")
    (bundle / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    package_bundle(bundle)


if __name__ == "__main__":
    main()
