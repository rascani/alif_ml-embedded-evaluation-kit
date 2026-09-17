#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates
# <open-source-office@arm.com>
# SPDX-License-Identifier: Apache-2.0
"""Program and measure four E8 Tiny images from a frozen artifact bundle."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import shutil
import subprocess
import sys
import tarfile
import time
from datetime import datetime
from pathlib import Path

from tflm_tiny_results import parse_boot, read_logs, write_results


def verify_bundle(bundle: Path) -> dict:
    """Check every packaged file before using firmware or metadata.

    :param bundle:      Extracted bundle directory.
    :returns:           Verified manifest.
    :raises ValueError: If a checksum or path is invalid.
    """
    for line in (bundle / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        expected, name = line.split("  ", 1)
        path = (bundle / name).resolve()
        if not path.is_relative_to(bundle.resolve()):
            raise ValueError(f"Invalid bundle path: {name}")
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f"Checksum mismatch: {name}")
    return json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))


def flash_model(bundle: Path, model_id: str, tools_dir: Path, port: str):
    """Package and program one firmware image using the installed SE Tools.

    :param bundle:      Verified bundle directory.
    :param model_id:    Model to program.
    :param tools_dir:   Existing SE Tools installation.
    :param port:        Programming serial device.
    :raises ValueError: If the installed device configuration cannot be preserved.
    """
    config_dir = tools_dir / "build/config"
    original = config_dir / "e8-smoke-tflm.json"
    if not original.exists():
        original = config_dir / "app-cfg.json"
    config = json.loads(original.read_text(encoding="utf-8"))
    if "DEVICE" not in config or config["DEVICE"].get("disabled", False):
        raise ValueError("Expected an enabled DEVICE entry in the installed SE Tools config")
    image_name = f"e8-tiny-{model_id}.bin"
    shutil.copy2(bundle / model_id / "mram.bin", tools_dir / "build/images" / image_name)
    package = {
        "DEVICE": config["DEVICE"],
        "HP_Tiny": {
            "disabled": False,
            "binary": image_name,
            "version": "1.0.0",
            "mramAddress": "0x80008000",
            "cpu_id": "M55_HP",
            "flags": ["boot"],
            "signed": False,
        },
    }
    config_path = config_dir / f"e8-tiny-{model_id}.json"
    config_path.write_text(json.dumps(package, indent=4) + "\n", encoding="utf-8")
    subprocess.run(
        [str(tools_dir / "app-gen-toc"), "-f", str(config_path)], cwd=tools_dir, check=True
    )
    subprocess.run([str(tools_dir / "app-write-mram"), "-c", port, "-p"], cwd=tools_dir, check=True)


def capture_model(bundle: Path, model_id: str, manifest: dict, args: argparse.Namespace) -> Path:
    """Capture the requested number of complete boots using one persistent serial handle.

    :param bundle:          Bundle root, used for default log placement.
    :param model_id:        Required firmware model identity.
    :param manifest:        Verified bundle manifest.
    :param args:            CLI serial, timeout, and boot-count options.
    :returns:               Raw UART log path.
    :raises ValueError:     If a boot belongs to another model or fails validation.
    :raises TimeoutError:   If the requested boots do not complete before the timeout.
    """
    serial = importlib.import_module("serial")
    log_dir = args.logs or bundle / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    output = log_dir / f"{model_id}-{datetime.now():%Y%m%d-%H%M%S-%f}.log"
    buffer = b""
    completed = 0
    deadline = time.monotonic() + args.timeout
    with serial.Serial(
        args.port,
        115200,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        timeout=0.25,
        xonxoff=False,
        rtscts=False,
        dsrdtr=False,
    ) as uart, output.open("xb") as log:
        print(
            f"Listening on {args.port}; log: {output}\n"
            f"Set SW4 to U4. Reset {args.boots} times, waiting for completion each time.",
            flush=True,
        )
        while completed < args.boots:
            if time.monotonic() > deadline:
                raise TimeoutError(
                    f"Only {completed}/{args.boots} boots captured; raw log: {output}"
                )
            data = uart.read(min(4096, uart.in_waiting or 1))
            if not data:
                continue
            log.write(data)
            log.flush()
            sys.stdout.buffer.write(data.replace(b"\n", b"\r\n"))
            sys.stdout.buffer.flush()
            buffer += data
            marker = b"program terminating..."
            while marker in buffer:
                boot, buffer = buffer.split(marker, 1)
                parse_boot((boot + marker).decode("utf-8", errors="replace"), manifest, model_id)
                completed += 1
                print(f"\nValidated {model_id} boot {completed}/{args.boots}.", flush=True)
                if completed == args.boots:
                    break
    print(f"Capture complete: {output}")
    return output


def collect_results(bundle: Path, output: Path | None) -> Path:
    """Archive results and raw logs without copying the firmware back from the board host.

    :param bundle:      Verified bundle directory with completed aggregate results.
    :param output:      Optional archive destination; existing files are never overwritten.
    :returns:           Created result archive.
    """
    paths = [bundle / name for name in ("manifest.json", "results.csv", "results.json", "logs")]
    for path in paths:
        if not path.exists():
            raise ValueError(f"Missing {path.name}; finish run all or summarize before collecting")
    archive = output or bundle.parent / (
        f"{bundle.name}-results-{datetime.now():%Y%m%d-%H%M%S}.tar.gz"
    )
    with tarfile.open(archive, "x:gz") as stream:
        for path in paths:
            stream.add(path, arcname=path.name)
    return archive


def execute(args: argparse.Namespace):
    """Execute the selected bundle action.

    :param args:    Parsed command-line options.
    """
    bundle = args.bundle.resolve()
    manifest = verify_bundle(bundle)
    if args.command == "collect":
        print(f"Results archive: {collect_results(bundle, args.output)}")
        return
    selected = list(manifest["models"]) if args.model == "all" else [args.model]
    if args.command in ("list", "verify"):
        for model_id in selected:
            row = manifest["models"][model_id]
            print(
                f"{model_id}: flash={row['flash_total_bytes']} bytes "
                f"model={row['bytes']} bytes sha256={row['sha256']}"
            )
        print("Bundle checksums OK")
        return
    if args.command in ("flash", "capture") and args.model == "all":
        raise ValueError("Select one model, or use run all to program and capture each model")
    if args.command == "summarize":
        paths = sorted((args.logs or bundle / "logs").glob("*.log"))
    else:
        paths = []
        for model_id in selected:
            if args.command in ("flash", "run"):
                input(f"Close other serial readers and set SW4 to SE for {model_id}; press Enter.")
                flash_model(bundle, model_id, args.tools.resolve(), args.port)
            if args.command in ("capture", "run"):
                paths.append(capture_model(bundle, model_id, manifest, args))
        if not paths:
            print(f"Now set SW4 to U4 and run: python3 run.py capture {args.model}")
            return
    output = args.output or bundle / (
        "results.csv" if args.model == "all" else f"{args.model}-results.csv"
    )
    rows = read_logs(paths, manifest)
    rows = [row for row in rows if row["model"] in selected]
    if not rows:
        raise ValueError("No logs matched the selected model")
    write_results(rows, output)
    print(f"Validated {len(rows)} boots. Results: {output} and {output.with_suffix('.json')}")


def main():
    """Run bundle verification, flashing, capture, or result aggregation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=("list", "verify", "flash", "capture", "run", "summarize", "collect")
    )
    parser.add_argument(
        "model", nargs="?", default="all", choices=("all", "ic", "vww", "kws", "ad")
    )
    parser.add_argument("--bundle", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--tools", type=Path, default=Path.home() / "app-release-exec-macos")
    parser.add_argument("--port", default="/dev/cu.usbmodem0012192765291")
    parser.add_argument("--logs", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--boots", type=int, default=3)
    parser.add_argument(
        "--timeout",
        type=float,
        default=600,
        help="Maximum capture seconds per model (default: 600)",
    )
    args = parser.parse_args()
    if args.boots < 1 or args.timeout <= 0:
        parser.error("--boots and --timeout must be positive")
    try:
        execute(args)
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Failed: {error}\n")
    except ModuleNotFoundError:
        parser.exit(1, "Capture requires pyserial: python3 -m pip install pyserial==3.5\n")
    except KeyboardInterrupt:
        parser.exit(130, "\nStopped; any raw capture is retained.\n")


if __name__ == "__main__":
    main()
