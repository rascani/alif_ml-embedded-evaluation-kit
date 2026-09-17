# SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates
# <open-source-office@arm.com>
# SPDX-License-Identifier: Apache-2.0
"""Select and verify E8 HP inference-pool placement without changing pool sizes."""

import json
from pathlib import Path
import re
import struct
import subprocess
import tempfile


def memory_options(placement: str) -> list[str]:
    """Select the GCC linker script for the requested inference memory.

    :param placement:   SRAM or DTCM placement.
    :returns:           CMake linker override.
    """
    suffix = "-dtcm" if placement == "dtcm" else ""
    return [f"-DLINKER_SCRIPT_NAME=RTSS-HP-infrun{suffix}"]


def pool_symbols(folder: Path, base: int, executorch: bool) -> dict:
    """Require exactly the expected address and reservation for each pool symbol.

    :param folder:      Snapshot containing demangled ELF symbols.
    :param base:        Expected pool base address.
    :param executorch:  Whether the temporary pool is also required.
    :returns:           Verified addresses and sizes by pool symbol name.
    :raises ValueError: If a pool is missing, moved or resized.
    """
    symbols = {}
    for line in (folder / "symbols.txt").read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([0-9a-f]+) ([0-9a-f]+) \w (.+)", line)
        if match:
            symbols[match[3]] = (int(match[1], 16), int(match[2], 16))
    expected = {"arm::app::activationBuf": (base, 262144)}
    if executorch:
        expected["sTmpAllocationPool"] = (base + 262144, 65536)
    for name, allocation in expected.items():
        if symbols.get(name) != allocation:
            raise ValueError(f"Unexpected inference pool: {name}: {symbols.get(name)}")
    return expected


def verify_zero_table(folder: Path, gcc_bin: Path, base: int, size: int):
    """Verify that startup clears the complete inference-pool reservation.

    :param folder:      Snapshot containing the linked ELF.
    :param gcc_bin:     Toolchain directory containing objcopy.
    :param base:        Pool output section address.
    :param size:        Pool output section size in bytes.
    :raises ValueError: If the startup zero table does not cover the pools.
    """
    with tempfile.TemporaryDirectory() as temporary:
        table = Path(temporary) / "zero-table.bin"
        subprocess.run(
            [str(gcc_bin / "arm-none-eabi-objcopy"), "-O", "binary",
             "--only-section=.zero.table.at_mram", str(folder / "mlek_inference_runner.axf"),
             str(table)], check=True,
        )
        entries = list(struct.iter_unpack("<II", table.read_bytes()))
    if (base, size // 4) not in entries:
        raise ValueError("Inference pools are absent from the startup zero table")


def audit_memory(folder: Path, placement: str, gcc_bin: Path, executorch: bool) -> dict:
    """Check pool symbols, zero initialization, and DTCM heap/stack separation.

    :param folder:      Snapshot containing ELF, section sizes, and symbols.
    :param placement:   Expected SRAM or DTCM placement.
    :param gcc_bin:     Toolchain directory containing objcopy.
    :param executorch:  Whether the temporary pool is also required.
    :returns:           Per-image placement and total reserved DTCM accounting.
    :raises ValueError: If the linked layout differs from the experiment.
    """
    sections = json.loads((folder / "sections.json").read_text(encoding="utf-8"))
    base = 0x20020000 if placement == "dtcm" else 0x02000000
    expected = pool_symbols(folder, base, executorch)
    total = sum(size for _, size in expected.values())
    pool_section = ".bss.inference" if placement == "dtcm" else ".bss.sram"
    if sections[pool_section] != {"bytes": total, "address": hex(base)}:
        raise ValueError("Unexpected inference output section")
    verify_zero_table(folder, gcc_bin, base, total)
    heap = sections[".heap"]
    stack = sections[".stack"]
    heap_end = int(heap["address"], 16) + heap["bytes"]
    stack_base = int(stack["address"], 16)
    if placement == "dtcm" and not heap_end <= base < base + total <= stack_base:
        raise ValueError("Inference pools overlap the heap or stack")
    dtcm = sum(
        section["bytes"] for section in sections.values()
        if 0x20000000 <= int(section["address"], 16) < 0x20100000
    )
    report = {
        "placement": placement,
        "pools": {name: {"address": hex(address), "bytes": size}
                  for name, (address, size) in expected.items()},
        "pool_reserved_bytes": total,
        "startup_zero_table_verified": True,
        "heap_end": hex(heap_end),
        "stack_base": hex(stack_base),
        "dtcm_reserved_bytes": dtcm,
        "dtcm_unallocated_bytes": 1048576 - dtcm,
    }
    (folder / "inference-memory.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    return report
