#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates
# <open-source-office@arm.com>
# SPDX-License-Identifier: Apache-2.0
"""Program, capture and collect the standalone Alif E8 timer diagnostic."""

import argparse
from datetime import datetime
import hashlib
import importlib
from pathlib import Path
import subprocess
import sys
import time

from alif_timer_results import parse_boot, write_results
from tflm_tiny_board import collect_results, flash_model, verify_bundle


def capture(args: argparse.Namespace, manifest: dict) -> list[dict]:
    """Capture and validate complete boots using a persistent UART handle.

    :param args:        CLI capture settings.
    :param manifest:    Verified bundle identity.
    :returns:           Validated boot records.
    """
    serial = importlib.import_module("serial")
    folder = args.bundle / "logs"
    folder.mkdir(exist_ok=True)
    path = folder / f"timer-{datetime.now():%Y%m%d-%H%M%S-%f}.log"
    deadline = time.monotonic() + args.timeout
    buffer = b""
    boots = []
    with serial.Serial(args.port, 115200, timeout=0.25, bytesize=serial.EIGHTBITS,
                       parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE,
                       xonxoff=False, rtscts=False, dsrdtr=False) as uart, path.open("xb") as log:
        print(f"Listening on {args.port}; raw log: {path}\n"
              f"Set SW4 to U4. Reset {args.boots} times; wait for completion each time.\n"
              "Each boot runs about 16 seconds plus UART output; "
              "the final test is quiet for 12 seconds.",
              flush=True)
        while len(boots) < args.boots:
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"Only {len(boots)}/{args.boots} boots; raw log retained at {path}")
            data = uart.read(min(4096, uart.in_waiting or 1))
            if not data:
                continue
            log.write(data)
            log.flush()
            sys.stdout.buffer.write(data.replace(b"\n", b"\r\n"))
            sys.stdout.buffer.flush()
            buffer += data
            marker = b"program terminating..."
            while marker in buffer and len(boots) < args.boots:
                text, buffer = buffer.split(marker, 1)
                boot = parse_boot((text + marker).decode("utf-8", errors="replace"), manifest)
                boot["source_log"] = str(path.relative_to(args.bundle))
                boots.append(boot)
                print(f"\nValidated timer boot {len(boots)}/{args.boots}.", flush=True)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    for boot in boots:
        boot["source_log_sha256"] = digest
    return boots


def summarize(paths: list[Path], manifest: dict) -> list[dict]:
    """Reparse explicitly selected complete captures without mixing earlier attempts.

    :param paths:       Selected raw log paths.
    :param manifest:    Expected firmware identity.
    :returns:           Independently validated boots.
    """
    if not paths:
        raise ValueError("Specify --logs to select the completed capture(s)")
    boots = []
    marker = "program terminating..."
    for path in paths:
        data = path.read_bytes()
        parts = data.decode("utf-8", errors="replace").split(marker)
        if parts[-1].strip():
            raise ValueError(f"Incomplete trailing boot in {path}")
        for part in parts[:-1]:
            boot = parse_boot(part + marker, manifest)
            boot.update(source_log=str(path), source_log_sha256=hashlib.sha256(data).hexdigest())
            boots.append(boot)
    return boots


def main():
    """Run verification, flashing, capture, replay or result collection."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command",
                        choices=("verify", "flash", "capture", "run", "summarize", "collect"))
    parser.add_argument("--bundle", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--tools", type=Path, default=Path.home() / "app-release-exec-macos")
    parser.add_argument("--port", default="/dev/cu.usbmodem0012192765291")
    parser.add_argument("--boots", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=600)
    parser.add_argument("--logs", type=Path, nargs="+", help="Explicit raw logs for summarize")
    args = parser.parse_args()
    args.bundle = args.bundle.resolve()
    if args.boots < 1 or args.timeout <= 0:
        parser.error("--boots and --timeout must be positive")
    try:
        manifest = verify_bundle(args.bundle)
        if args.command == "verify":
            print(f"Bundle verified: {manifest['build_id']}")
        elif args.command == "collect":
            print(f"Results archive: {collect_results(args.bundle, None)}")
        else:
            if args.command in ("run", "flash"):
                input("Close other serial readers; set SW4 to SE and press Enter.")
                flash_model(args.bundle, "timer", args.tools.resolve(), args.port)
            if args.command in ("run", "capture"):
                boots = capture(args, manifest)
                write_results(boots, args.bundle)
                print(f"Validated {len(boots)} boots. Results: {args.bundle / 'results.json'}")
            elif args.command == "summarize":
                boots = summarize(args.logs, manifest)
                write_results(boots, args.bundle)
                print(f"Validated {len(boots)} boots")
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Failed: {error}\n")
    except ModuleNotFoundError:
        parser.exit(1, "Capture requires: python3 -m pip install pyserial==3.5\n")
    except KeyboardInterrupt:
        parser.exit(130, "\nStopped; raw capture is retained.\n")


if __name__ == "__main__":
    main()
