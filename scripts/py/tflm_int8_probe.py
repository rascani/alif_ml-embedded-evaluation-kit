# SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates
# <open-source-office@arm.com>
# SPDX-License-Identifier: Apache-2.0
"""Compare selected and generic CMSIS-NN registrations using the same M55 libraries."""

import argparse
import json
import os
from pathlib import Path
import re
import shlex
import subprocess

from mlek_tools.gen.gen_tflm_resolver import generate_resolver


def compare_int8(args: argparse.Namespace, model_id: str, link: list[str]) -> dict:
    """Check distinct callbacks and exact outputs on eight inputs in a separate FVP image.

    :param args:        Bundle/build/toolchain/simulator paths.
    :param model_id:    Model whose build tree is currently configured.
    :param link:        Semihosting link command for the existing E8 archives.
    :returns:           Probe identity and output hashes, without performance claims.
    """
    root = Path(__file__).resolve().parents[2]
    output = args.bundle / "validation/fvp" / f"{model_id}-int8"
    output.mkdir(exist_ok=True)
    model = next((args.bundle / model_id).glob("*.tflite"))
    resolver = root / "dependencies/tensorflow/tensorflow/lite/micro/micro_mutable_op_resolver.h"
    generate_resolver(model, resolver, output)
    generic = (output / "SelectedTflmModel.hpp").read_text(encoding="utf-8")
    generic = generic.replace("SelectedTflmModel", "GenericTflmModel")
    generic = generic.replace("MLEK_SELECTED_TFLM_MODEL_HPP", "MLEK_GENERIC_TFLM_MODEL_HPP")
    (output / "GenericTflmModel.hpp").write_text(generic, encoding="utf-8")
    # The real selected header must resolve from the E8 build include path.
    (output / "SelectedTflmModel.hpp").unlink()
    executable = compile_probe(args, output, link)
    text = run_probe(args.fvp, executable, output / "run.log")
    samples = re.findall(r"INT8_COMPARE sample=(\d+) status=PASS output_fnv1a=([0-9a-f]+)", text)
    summary = re.findall(r"INT8_COMPARE summary samples=8 operators=(\d+) status=PASS", text)
    selected = json.loads((args.bundle / model_id / "selected_tflm_operators.json").read_text())
    expected = sum(bool(op["registration"]) for op in selected["operators"])
    if [int(index) for index, _ in samples] != list(range(8)) or summary != [str(expected)]:
        raise ValueError(f"{model_id}: missing specialization or unequal M55 outputs")
    return {"status": "PASS", "samples": 8, "specialized_callbacks": expected,
            "output_fnv1a": [value for _, value in samples]}


def compile_probe(args: argparse.Namespace, output: Path, link: list[str]) -> Path:
    """Compile the comparison with actual E8 definitions, then link existing runtime archives.

    :param args:    Build directory and toolchain paths.
    :param output:  Probe source support and logs.
    :param link:    Base semihosting link command.
    :returns:       Comparison executable.
    """
    root = Path(__file__).resolve().parents[2]
    commands = json.loads((args.build / "compile_commands.json").read_text(encoding="utf-8"))
    row = next(
        item for item in commands if item["file"].endswith("/inference_runner/src/MainLoop.cc")
    )
    command = shlex.split(row["command"])
    if "-DCMSIS_NN" not in command:
        raise ValueError("CMSIS_NN must be defined to test specialized registrations")
    source = root / "tests/integration/tiny_fvp/int8_registration.cpp"
    obj = output / "int8_registration.o"
    command[command.index("-o") + 1] = str(obj)
    command[command.index("-c") + 1] = str(source)
    command += ["-I", str(output)]
    with (output / "compile.log").open("w", encoding="utf-8") as log:
        subprocess.run(command, cwd=args.build, stdout=log, stderr=subprocess.STDOUT, check=True)
    executable = output / "compare.axf"
    command = [str(obj) if arg.endswith("/tiny_fvp/main.cpp") else arg for arg in link]
    command += ["-o", str(executable)]
    (output / "link.json").write_text(json.dumps(command, indent=2) + "\n", encoding="utf-8")
    with (output / "link.log").open("w", encoding="utf-8") as log:
        subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
    return executable


def run_probe(fvp: Path, executable: Path, log: Path) -> str:
    """Execute a bounded Corstone-300 probe and retain its complete output.

    :param fvp:         Simulator executable.
    :param executable:  Probe ELF.
    :param log:         Output path.
    :returns:           Simulator log text.
    """
    with log.open("w", encoding="utf-8") as stream:
        subprocess.run([
            str(fvp), "-C", "mps3_board.visualisation.disable-visualisation=1",
            "-C", "mps3_board.telnetterminal0.start_telnet=0", "-C", "cpu0.semihosting-enable=1",
            "-C", "cpu0.semihosting-stack_base=0", "-C", "cpu0.semihosting-heap_limit=0",
            "-a", str(executable), "--timelimit", "60",
        ], stdout=stream, stderr=subprocess.STDOUT, check=True, timeout=70, env=dict(os.environ))
    return log.read_text(encoding="utf-8")
