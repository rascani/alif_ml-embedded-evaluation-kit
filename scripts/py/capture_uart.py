#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates
# <open-source-office@arm.com>
# SPDX-License-Identifier: Apache-2.0
"""Capture a UART with persistent 115200 8N1 settings and readable LF output.

Requires pyserial. Received bytes are appended unchanged to the output file;
only the console display adds carriage returns before line feeds.
"""

import argparse
import sys
from pathlib import Path

import serial


def capture(port: str, output: Path):
    """Configure and read the same serial handle until interrupted.

    :param port:    Serial device path.
    :param output:  Raw UART log to append to.
    """
    # PySerial defaults to 8N1 with software and hardware flow control disabled.
    with serial.Serial(port, 115200, timeout=0.25) as uart, output.open("ab", buffering=0) as log:
        print(
            f"Listening on {port} at 115200 8N1; raw log: {output}\n"
            "Set SW4 to U4 and reset the board now. Ctrl-C stops capture.",
            file=sys.stderr,
            flush=True,
        )
        try:
            while True:
                data = uart.read(min(4096, uart.in_waiting or 1))
                if data:
                    log.write(data)
                    # Explicit CR also works when terminal output processing is disabled.
                    sys.stdout.buffer.write(data.replace(b"\n", b"\r\n"))
                    sys.stdout.buffer.flush()
        except KeyboardInterrupt:
            print("\nCapture stopped.", file=sys.stderr)


def main():
    """Parse the serial device and output file arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        capture(args.port, args.output)
    except (serial.SerialException, OSError) as error:
        parser.exit(1, f"Capture failed: {error}\n")


if __name__ == "__main__":
    main()
