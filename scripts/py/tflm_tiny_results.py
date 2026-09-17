# SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates
# <open-source-office@arm.com>
# SPDX-License-Identifier: Apache-2.0
"""Validate E8 Tiny UART records and combine latency, flash, and RAM measurements."""

from __future__ import annotations

import csv
import json
import math
import re
import statistics
from pathlib import Path


def fields(text: str, prefix: str) -> dict[str, str]:
    """Read exactly one record with the specified prefix.

    :param text:        One complete boot's console output.
    :param prefix:      Record prefix following the log level.
    :returns:           Key/value fields from that record.
    :raises ValueError: If the record is missing or duplicated.
    """
    matches = re.findall(re.escape(prefix) + r" ([^\r\n]*)", text)
    if len(matches) != 1:
        raise ValueError(f"Expected one {prefix} record, found {len(matches)}")
    return dict(re.findall(r"(\w+)=([^\s]+)", matches[0]))


def parse_boot(text: str, manifest: dict, expected_model: str | None = None) -> dict:
    """Validate one completed board run and calculate a result row.

    :param text:            Complete boot log, including termination.
    :param manifest:        Frozen bundle manifest.
    :param expected_model:  Optional model ID required by the capture command.
    :returns:               Latency and memory record, with original cycle samples.
    :raises ValueError:     If identity, counts, units, summaries, or completion are invalid.
    """
    if "build_id" in manifest and fields(text, "BENCHMARK build")["id"] != manifest["build_id"]:
        raise ValueError("Firmware build identity differs from the bundle")
    identity = fields(text, "BENCHMARK model")
    model_id = identity["id"]
    if model_id not in manifest["models"] or (
        expected_model is not None and model_id != expected_model
    ):
        raise ValueError(f"Wrong firmware model: {model_id}; expected {expected_model}")
    model = manifest["models"][model_id]
    if identity["sha256"] != model["sha256"] or int(identity["bytes"]) != model["bytes"]:
        raise ValueError("Embedded model identity differs from the bundle")
    row = timing_record(text, manifest["benchmark"])
    row.update(model=model_id, model_sha256=identity["sha256"])
    if "build_id" in manifest:
        row["build_id"] = manifest["build_id"]
    row.update(
        {
            key: model[key]
            for key in ("flash_total_bytes", "flash_model_bytes", "flash_non_model_bytes")
        }
    )
    if manifest.get("framework") == "ExecuTorch":
        row.update(et_memory_record(text, model))
        validate_outputs(text, model["validation_samples"],
                         model.get("validation_reference", "lowered_python_int8"))
        row["validation_samples"] = model["validation_samples"]
    else:
        row.update(memory_record(text))
    row.update({key: value for key, value in model.items() if key.startswith("flash_")})
    return row


def timing_record(text: str, benchmark: dict) -> dict:
    """Validate timer samples and derive microseconds.

    :param text:        Boot text.
    :param benchmark:   Expected iteration settings.
    :returns:           Timing record and sample values.
    """
    config = fields(text, "BENCHMARK config")
    expected = benchmark
    count = int(config["measured"])
    if (
        config["input"] != "synthetic_v1"
        or config["version"] != "1"
        or count != expected["measurements"]
        or int(config["warmups"]) != expected["warmups"]
    ):
        raise ValueError("Unexpected benchmark configuration")
    clock = re.findall(r"Processor internal clock: (\d+)Hz", text)
    totals = re.findall(r"Total number of inferences: (\d+)", text)
    if len(clock) != 1 or int(clock[0]) <= 0 or totals != [str(1 + count + expected["warmups"])]:
        raise ValueError("Missing clock or incorrect invocation count")
    if "Inference completed." not in text or "program terminating..." not in text:
        raise ValueError("Inference did not complete")
    samples = re.findall(r"BENCHMARK sample index=(\d+) value=(\d+) unit=(\w+)", text)
    if [int(index) for index, _, _ in samples] != list(range(count)):
        raise ValueError("Missing, duplicated, or unordered samples")
    if any(unit != "cycles" for _, _, unit in samples):
        raise ValueError("Board results must be measured in cycles")
    values = [int(value) for _, value, _ in samples]
    summary = fields(text, "BENCHMARK summary")
    first = fields(text, "BENCHMARK first")
    if first["unit"] != "cycles" or summary["unit"] != "cycles":
        raise ValueError("Incorrect timer units")
    calculated = {
        "count": count,
        "min": min(values),
        "mean": statistics.mean(values),
        "median": statistics.median(values),
        "max": max(values),
        "p95": sorted(values)[math.ceil(0.95 * count) - 1],
    }
    if any(
        not math.isfinite(float(summary[key])) or abs(float(summary[key]) - value) > 0.00051
        for key, value in calculated.items()
    ):
        raise ValueError("Firmware summary does not match its samples")
    scale = 1_000_000 / int(clock[0])
    row = {
        "clock_hz": int(clock[0]),
        "count": count,
        "first_us": int(first["value"]) * scale,
    }
    row.update({f"{key}_us": value * scale for key, value in calculated.items() if key != "count"})
    row["samples_cycles"] = values
    return row


def memory_record(text: str) -> dict:
    """Validate memory totals without counting the persistent tail twice.

    :param text:    Boot text.
    :returns:       Arena and outside-persistent costs.
    """
    arena = {key: int(value) for key, value in fields(text, "MEMORY arena").items()}
    outside = {key: int(value) for key, value in fields(text, "MEMORY outside").items()}
    total = {key: int(value) for key, value in fields(text, "MEMORY total").items()}
    if (
        arena["raw_peak"] != arena["peak"] + arena["audit_overhead"]
        or arena["peak"] != max(arena["init_peak"], arena["invoke_peak"])
        or arena["raw_peak"] > arena["reserved"]
    ):
        raise ValueError("Inconsistent arena accounting")
    if (
        outside["persistent"] != outside["model_object"] + outside["init_heap_delta"]
        or total["inference_peak"] != arena["invoke_peak"] + outside["persistent"]
        or total["lifecycle_arena_plus_persistent"] != arena["peak"] + outside["persistent"]
    ):
        raise ValueError("Inconsistent memory accounting")
    row = {}
    row.update(
        {
            f"arena_{key}_bytes": value
            for key, value in arena.items()
            if key != "invoke_allocation_calls"
        }
    )
    row.update({f"outside_{key}_bytes": value for key, value in outside.items()})
    row.update({f"ram_{key}_bytes": value for key, value in total.items()})
    row["invoke_allocation_calls"] = arena["invoke_allocation_calls"]
    return row


def et_memory_record(text: str, model: dict) -> dict:
    """Check disjoint RAM terms and include linked runtime static storage.

    :param text:    Complete boot log.
    :param model:   Frozen model metadata and ELF static RAM accounting.
    :returns:       Flat byte counts for CSV and JSON results.
    """
    records = {
        name: {key: int(value) for key, value in fields(text, f"MEMORY et_{name}").items()}
        for name in ("method", "temp", "outside", "total")
    }
    method, temp, outside, total = (records[key] for key in records)
    init = {key: int(value) for key, value in fields(text, "MEMORY et_init").items()}
    if any(value < 0 for record in records.values() for value in record.values()):
        raise ValueError("Negative ExecuTorch RAM accounting")
    if (
        method["planned"] != model["planned_bytes"]
        or method["used"] != method["planned"] + method["runtime_and_inputs"]
        or method["peak"] != method["used"]
        or method["reserved"] != model["arena_reserved_bytes"]
        or method["peak"] > method["reserved"]
    ):
        raise ValueError("Inconsistent ExecuTorch method pool")
    if (
        temp["reserved"] != model["temp_reserved_bytes"]
        or temp["used"] > temp["peak"]
        or temp["peak"] > temp["reserved"]
        or init["method_peak"] != method["used"]
        or not 0 <= init["temp_peak"] <= temp["reserved"]
    ):
        raise ValueError("Inconsistent ExecuTorch temporary pool or initialization")
    if (
        outside["persistent"] != outside["model_object"] + outside["init_heap_delta"]
        or total["pools_plus_persistent"] != method["peak"] + temp["peak"] + outside["persistent"]
    ):
        raise ValueError("Inconsistent ExecuTorch heap or RAM total")
    row = {
        f"et_{name}_{key}_bytes": value
        for name, record in records.items()
        for key, value in record.items()
    }
    row["runtime_static_bytes"] = model["runtime_static_bytes"]
    if "input_pool_allocation_bytes" in model:
        allocations = re.findall(r"Inputs allocated: (\d+) bytes\.", text)
        if allocations != [str(model["input_pool_allocation_bytes"])]:
            raise ValueError("Unexpected ExecuTorch input allocation")
        row["input_pool_allocation_bytes"] = int(allocations[0])
    row.update({f"et_init_{key}_bytes": value for key, value in init.items()})
    row.update(et_heap_record(text, model.get("heap_measurement_scope", "handler_v1")))
    row["ram_accounted_peak_bytes"] = total["pools_plus_persistent"] + model["runtime_static_bytes"]
    return row


def et_heap_record(text: str, expected_scope: str) -> dict:
    """Require stable inference heap while reporting formatting allocations separately.

    :param text:            Complete boot log.
    :param expected_scope:  Measurement boundary specified by the firmware manifest.
    :returns:               Heap scope and retained deltas in bytes.
    :raises ValueError:     If the scope differs, inference heap changes, or fields are invalid.
    """
    invoke = fields(text, "MEMORY et_invoke")
    scope = invoke.get("scope", "handler_v1")
    if scope != expected_scope or scope not in ("handler_v1", "inference_batch_v1"):
        raise ValueError("Unexpected ExecuTorch heap measurement scope")
    before, after = int(invoke["heap_before"]), int(invoke["heap_after"])
    if before < 0 or before != after:
        raise ValueError(f"ExecuTorch heap changed in {scope}: {before} -> {after}")
    row = {"invoke_heap_scope": scope, "invoke_heap_delta_bytes": after - before}
    if scope == "inference_batch_v1":
        diagnostics = fields(text, "MEMORY et_diagnostics")
        before, after = int(diagnostics["heap_before"]), int(diagnostics["heap_after"])
        if min(before, after) < 0:
            raise ValueError("Negative diagnostic heap accounting")
        row["diagnostic_heap_delta_bytes"] = after - before
    return row


def validate_outputs(text: str, count: int, reference: str = "lowered_python_int8"):
    """Require every expected sample to match the manifest's saved reference output.

    :param text:        Complete boot log.
    :param count:       Expected number of validation samples.
    :param reference:   Exact reference identity recorded by the export.
    :raises ValueError: If a check is missing, duplicated, failed, or uses another reference.
    """
    samples = re.findall(r"VALIDATION sample index=(\d+) status=(\w+)", text)
    summary = fields(text, "VALIDATION summary")
    if samples != [(str(index), "PASS") for index in range(count)] or summary != {
        "count": str(count),
        "status": "PASS",
        "reference": reference,
    }:
        raise ValueError("ExecuTorch output validation failed or is incomplete")


def read_logs(paths: list[Path], manifest: dict) -> list[dict]:
    """Validate every complete boot and reject incomplete trailing output.

    :param paths:       UART log paths.
    :param manifest:    Bundle manifest.
    :returns:           Per-boot records with log filename and boot index.
    :raises ValueError: If a boot is invalid or a capture is incomplete.
    """
    rows = []
    marker = "program terminating..."
    for path in paths:
        chunks = path.read_text(encoding="utf-8", errors="replace").split(marker)
        if chunks[-1].strip():
            raise ValueError(f"Incomplete final boot in {path}")
        for index, chunk in enumerate(chunks[:-1], 1):
            row = parse_boot(chunk + marker, manifest)
            row.update(log=str(path), boot=index)
            rows.append(row)
    if not rows:
        raise ValueError("No complete benchmark boots found")
    return rows


def write_results(rows: list[dict], output: Path):
    """Write a CSV plus JSON retaining the complete sample lists.

    :param rows:    Validated per-boot records.
    :param output:  Destination CSV filename; JSON uses the same stem.
    """
    output.parent.mkdir(parents=True, exist_ok=True)
    columns = [key for key in rows[0] if key != "samples_cycles"]
    with output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    output.with_suffix(".json").write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
