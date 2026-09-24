#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates
# <open-source-office@arm.com>
# SPDX-License-Identifier: Apache-2.0
"""Attribute stored E8 Tiny image bytes using GNU linker-map input sections."""

from __future__ import annotations

import argparse
from collections import Counter
import csv
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import re

from tflm_tiny_board import verify_bundle

LIBRARY_CATEGORIES = {
    "libcmsis-nn.a": "cmsis_nn",
    "libml_framework_tflm.a": "framework_adapter",
    "libprofiler.a": "runner_diagnostics",
    "Main.cc.obj": "runner_diagnostics",
    **dict.fromkeys(
        ("libstdc++.a", "libg.a", "libc.a", "libm.a", "libgcc.a", "libnosys.a"),
        "shared_toolchain",
    ),
    **dict.fromkeys(
        (
            "libcmsis_device.a",
            "libplatform_drivers_core.a",
            "libalif_se_services.a",
            "libhal_display_stubs.a",
            "libhal.a",
        ),
        "platform_startup",
    ),
}


@dataclass
class Contribution:
    """One retained input section, with byte counts after linker relaxation."""

    section: str
    input_section: str
    address: int
    size: int
    owner: str


def parse_map(text: str, sections: dict) -> list[Contribution]:
    """Read retained input sections in the selected loadable output sections.

    :param text:        GNU linker map, including its discarded-section preamble.
    :param sections:    Stored ELF sections with virtual addresses and sizes.
    :returns:           Non-overlapping contributions within those sections.
    :raises ValueError: If an input range overlaps another or lies outside its section.
    """
    text = text.split("Linker script and memory map", 1)[1]
    entries = []
    current = ""
    pending = ""
    input_line = re.compile(r"^ ([.A-Za-z_][^\s]*)(?:\s+(0x[0-9a-f]+)\s+(0x[0-9a-f]+)\s+(.+))?$")
    continuation = re.compile(
        r"^\s+(0x[0-9a-f]+)\s+(0x[0-9a-f]+)\s+(\S+\.(?:a\([^)]*\)|o|obj))\s*$"
    )
    for line in text.splitlines():
        if line.startswith("."):
            current = line.split()[0]
            pending = ""
        if current not in sections:
            continue
        match = input_line.match(line)
        if match:
            pending = match[1]
            if match[2] is None:
                continue
            address, size, owner = match.group(2, 3, 4)
        else:
            match = continuation.match(line)
            if not match or not pending:
                continue
            address, size, owner = match.groups()
        if int(size, 16):
            entries.append(Contribution(current, pending, int(address, 16), int(size, 16), owner))
        pending = ""
    validate_ranges(entries, sections)
    return entries


def validate_ranges(entries: list[Contribution], sections: dict):
    """Reject overlaps and entries that extend beyond their stored ELF section.

    :param entries:     Map contributions to check.
    :param sections:    Expected output section bounds.
    :raises ValueError: If a contribution overlaps another or crosses a section boundary.
    """
    for name, section in sections.items():
        start = int(section["address"], 16)
        previous_end = start
        for entry in sorted((e for e in entries if e.section == name), key=lambda e: e.address):
            if (
                entry.address < previous_end
                or entry.address + entry.size > start + section["bytes"]
            ):
                raise ValueError(f"Overlapping or out-of-section map contribution: {entry}")
            previous_end = entry.address + entry.size


def is_merged_string_section(section: str) -> bool:
    """Identify ordinary and function-qualified GCC mergeable string sections.

    :param section: Input-section name from the linker map.
    :returns:       Whether the section uses GCC's string-pool naming convention.
    """
    return re.fullmatch(r"\.rodata(?:\.[^\s]+)?\.str[1248]\.\d+", section) is not None


def category(entry: Contribution) -> str:
    """Assign a retained contribution to an explicit ownership bucket.

    :param entry:   Retained input section.
    :returns:       Accounting category; shared support is never charged entirely to TFLM.
    """
    library = Path(entry.owner.split("(", 1)[0]).name
    member = entry.owner.partition("(")[2].removesuffix(")")
    if entry.input_section == "nn_model":
        return "model"
    if is_merged_string_section(entry.input_section):
        return "shared_merged_strings"
    if library == "libtflu.a":
        logging_members = (
            "debug_log.cc.obj",
            "micro_log.cc.obj",
            "micro_error_reporter.cc.obj",
            "error_reporter.cc.obj",
        )
        return "framework_logging" if member in logging_members else "tflm"
    if library == "libinference_runner.a":
        # Header-defined resolver methods are emitted into the application's object.
        if member == "MainLoop.cc.obj" and (
            "MicroMutableOpResolver" in entry.input_section
            or (
                "SelectedTflmModel" in entry.input_section
                and any(
                    name in entry.input_section for name in ("EnlistOperations", "GetOpResolver")
                )
            )
        ):
            return "selected_resolver"
        return "runner_diagnostics"
    return LIBRARY_CATEGORIES.get(
        library, "platform_startup" if library.startswith("crt") else "other"
    )


def analyze_model(folder: Path, model: dict) -> tuple[dict, list[dict]]:
    """Reconcile attributed contributions to the exact model and MRAM payload sizes.

    :param folder:      Frozen model artifact directory.
    :param model:       Manifest model and image metadata.
    :returns:           Summary fields and an auditable list of input-section contributions.
    :raises ValueError: If model bytes, stored section bounds or totals do not reconcile.
    """
    sections = json.loads((folder / "sections.json").read_text(encoding="utf-8"))
    sections = {name: value for name, value in sections.items() if name.endswith(".at_mram")}
    entries = parse_map(
        (folder / "mlek_inference_runner.map").read_text(encoding="utf-8"), sections
    )
    groups = Counter()
    details = []
    for entry in entries:
        group = category(entry)
        groups[group] += entry.size
        details.append({**asdict(entry), "category": group})
    stored_size = sum(section["bytes"] for section in sections.values())
    internal_gaps = stored_size - sum(groups.values())
    image_size = (folder / "mram.bin").stat().st_size
    external_gaps = image_size - stored_size
    if internal_gaps < 0 or external_gaps < 0 or image_size != model["flash_total_bytes"]:
        raise ValueError("Stored ELF sections do not reconcile with the MRAM payload")
    if groups["model"] != model["bytes"] or groups["other"]:
        raise ValueError("Unexpected model size or unclassified object; inspect the linker map")
    groups["linker_tables_padding"] = internal_gaps + external_gaps
    filtered_runtime = sum(groups[key] for key in ("tflm", "cmsis_nn", "selected_resolver"))
    result = {f"{name}_bytes": value for name, value in sorted(groups.items())}
    result.update(
        filtered_runtime_bytes=filtered_runtime,
        filtered_model_runtime_bytes=groups["model"] + filtered_runtime,
        full_image_bytes=image_size,
        excluded_from_filtered_bytes=image_size - groups["model"] - filtered_runtime,
        stored_section_bytes=stored_size,
        intra_section_unattributed_bytes=internal_gaps,
        inter_section_padding_bytes=external_gaps,
        elf_sha256=hashlib.sha256((folder / "mlek_inference_runner.axf").read_bytes()).hexdigest(),
        map_sha256=hashlib.sha256((folder / "mlek_inference_runner.map").read_bytes()).hexdigest(),
    )
    return result, details


def main():
    """Verify the original bundle and emit filtered sizes plus a full reconciliation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    manifest = verify_bundle(args.bundle)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    result = {
        "schema_version": 1,
        "method": "GNU linker-map retained input sections; only stored .at_mram outputs.",
        "definitions": {
            "filtered_runtime_bytes": (
                "TFLM library (excluding dedicated logging objects) + CMSIS-NN + "
                "separately emitted model-specific resolver code/data."
            ),
            "filtered_model_runtime_bytes": "Exact embedded model bytes + filtered_runtime_bytes.",
            "shared_toolchain_bytes": (
                "All linked libc/libstdc++/libm/libgcc objects; shared inference and "
                "application support, not assigned entirely to either."
            ),
            "shared_merged_strings_bytes": (
                "Merged string sections shared across objects; GNU ld assigns their "
                "entire pool to its first input, so no single component is charged."
            ),
            "framework_adapter_bytes": (
                "MLEK TflmModel/TflmTensor integration including its logging; reported separately."
            ),
            "linker_tables_padding_bytes": (
                "Linker-generated tables, alignment and otherwise unowned section bytes."
            ),
        },
        "limitations": [
            "Ownership attribution in the measured logging-enabled image, not a standalone "
            "deployable runtime size or guaranteed removable byte count.",
            "Inline diagnostic call sites and non-merged strings within retained runtime "
            "objects remain included; merged string pools are separate shared support.",
            "COMDAT helpers are assigned to the object retained by the linker; "
            "this does not establish exclusive use.",
            "Some excluded shared toolchain support and application integration are required "
            "to deploy inference.",
        ],
        "models": {},
    }
    csv_rows = []
    for name, model in manifest["models"].items():
        summary, details = analyze_model(args.bundle / name, model)
        result["models"][name] = summary
        csv_rows.append({"model": name, **summary})
        (args.output_dir / f"{name}-contributions.json").write_text(
            json.dumps(details, indent=2) + "\n", encoding="utf-8"
        )
    (args.output_dir / "summary.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    with (args.output_dir / "summary.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(csv_rows[0]))
        writer.writeheader()
        writer.writerows(csv_rows)
    print(json.dumps(result["models"], indent=2))


if __name__ == "__main__":
    main()
