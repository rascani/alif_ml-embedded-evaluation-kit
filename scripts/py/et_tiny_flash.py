# SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates
# <open-source-office@arm.com>
# SPDX-License-Identifier: Apache-2.0
"""Reconcile ET model/runtime flash and runtime static RAM from retained input sections."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict
import json
from pathlib import Path

from tflm_tiny_flash import (
    Contribution,
    category as shared_category,
    is_merged_string_section,
    parse_map,
)

RUNTIME_GROUPS = ("executorch_core", "kernels", "cmsis_nn", "registry")


def category(entry: Contribution) -> str:
    """Classify linked ET runtime sections consistently with the TFLM ownership report.

    :param entry:   Retained map contribution.
    :returns:       Ownership category.
    """
    library = Path(entry.owner.split("(", 1)[0]).name
    member = entry.owner.partition("(")[2].removesuffix(")")
    if "kValidationInputs" in entry.input_section or "kValidationOutputs" in entry.input_section:
        return "validation_fixtures"
    if is_merged_string_section(entry.input_section):
        return "shared_merged_strings"
    if library in ("libexecutorch.a", "libexecutorch_core.a"):
        return {
            "operator_registry.cpp.obj": "registry",
            "register_prim_ops.cpp.obj": "registry",
            "log.cpp.obj": "framework_logging",
            "tensor_shape_to_c_string.cpp.obj": "framework_logging",
            "minimal.cpp.obj": "platform_startup",
            "platform.cpp.obj": "platform_startup",
        }.get(member, "executorch_core")
    if library.startswith("libinference_runner_portable_ops_lib"):
        return "registry"
    if "kernels" in library or library.startswith("libcortex_m"):
        return "kernels"
    return {
        "libml_framework_et.a": "framework_adapter",
        "libextension_runner_util.a": "framework_adapter",
        "EtPal.cc.obj": "platform_startup",
    }.get(library, shared_category(entry))


def analyze_model(folder: Path, model: dict) -> dict:
    """Write auditable attribution details and return flash plus static RAM totals.

    :param folder:      Model ELF, map, and section metadata directory.
    :param model:       PTE size, full image size, and embedded validation fixture size.
    :returns:           Manifest fields, all in bytes.
    :raises ValueError: If model bytes, fixtures, unknown owners, or total sizes disagree.
    """
    sections = json.loads((folder / "sections.json").read_text(encoding="utf-8"))
    text = (folder / "mlek_inference_runner.map").read_text(encoding="utf-8")
    stored = {key: value for key, value in sections.items() if key.endswith(".at_mram")}
    entries = parse_map(text, stored)
    details = [dict(asdict(entry), category=category(entry)) for entry in entries]
    groups = Counter()
    for row in details:
        groups[row["category"]] += row["size"]
    if groups["other"]:
        raise ValueError(
            f"Unclassified flash: {[row for row in details if row['category'] == 'other']}"
        )
    if (
        groups["model"] != model["bytes"]
        or groups["validation_fixtures"] != model["validation_fixture_bytes"]
    ):
        raise ValueError("Model or validation fixture byte count differs from the linked image")
    payload = model["flash_total_bytes"]
    if not sum(groups.values()) <= sum(row["bytes"] for row in stored.values()) <= payload:
        raise ValueError("Flash section totals exceed the image")
    groups["linker_tables_padding"] = payload - sum(groups.values())
    runtime = sum(groups[key] for key in RUNTIME_GROUPS)
    ram_sections = {
        key: value for key, value in sections.items() if key in (".bss", ".data.dtcm.at_mram")
    }
    ram_details = [
        dict(asdict(entry), category=category(entry))
        for entry in parse_map(text, ram_sections)
        if category(entry) in RUNTIME_GROUPS
    ]
    report = {
        "flash": dict(groups),
        "runtime_static_bytes": sum(row["size"] for row in ram_details),
        "runtime_static_contributions": ram_details,
        "flash_contributions": details,
    }
    (folder / "memory-attribution.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    return {
        "flash_runtime_filtered_bytes": runtime,
        "flash_model_plus_runtime_bytes": model["bytes"] + runtime,
        **{f"flash_{key}_bytes": groups[key] for key in RUNTIME_GROUPS},
        "flash_validation_fixtures_bytes": groups["validation_fixtures"],
        "flash_shared_merged_strings_bytes": groups["shared_merged_strings"],
        "runtime_static_bytes": report["runtime_static_bytes"],
    }
