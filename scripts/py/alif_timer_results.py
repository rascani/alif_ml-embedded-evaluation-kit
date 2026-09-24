# SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates
# <open-source-office@arm.com>
# SPDX-License-Identifier: Apache-2.0
"""Independently validate bracketed DWT/SysTick/CPU TOTAL measurements."""

import csv
import json
from pathlib import Path
import re

DURATIONS = [value for value in (0, 100, 900, 1100, 10000, 100000, 1000000) for _ in range(3)]
CASES = [("interval", duration) for duration in DURATIONS] + [
    ("dwt_wrap", 10000), ("pending", 250), ("long", 12000000)]


def records(text: str, kind: str) -> list[dict[str, str]]:
    """Parse records while rejecting duplicate or malformed fields.

    :param text:    UART text for one boot.
    :param kind:    Record type after TIMER.
    :returns:       Parsed records.
    """
    result = []
    for line in re.findall(rf"TIMER {kind} ([^\r\n]*)", text):
        pairs = [token.split("=", 1) for token in line.split()]
        if any(len(pair) != 2 for pair in pairs):
            raise ValueError(f"Malformed TIMER {kind}")
        record = dict(pairs)
        if len(record) != len(pairs):
            raise ValueError(f"Duplicate TIMER {kind} field")
        result.append(record)
    return result


def single(text: str, kind: str) -> dict[str, str]:
    """Require exactly one configuration, identity or completion record.

    :param text:    UART text.
    :param kind:    Record type.
    :returns:       The unique record.
    """
    rows = records(text, kind)
    if len(rows) != 1:
        raise ValueError(f"Expected one TIMER {kind}, found {len(rows)}")
    return rows[0]


def validate_coverage(row: dict, target: int, period: int, bounds: tuple[int, int]):
    """Require the intended duration, interrupt servicing and rollover coverage.

    :param row:     Parsed sample, updated with interrupt count.
    :param target:  Requested duration in cycles.
    :param period:  SysTick period in cycles.
    :param bounds:  DWT lower and upper elapsed-cycle bounds.
    """
    lower, upper = bounds
    if lower < target:
        raise ValueError("Interval shorter than requested")
    if row["pending_start"] not in (0, 1) or row["pending_end"] not in (0, 1):
        raise ValueError("Invalid pending-interrupt flag")
    interrupts = (row["irq_end"] - row["irq_start"]) & 0xffffffff
    if row["kind"] == "pending":
        if row["pending_start"] or not row["pending_end"] or interrupts or upper >= period:
            raise ValueError("Pending-wrap case did not exercise one bounded masked wrap")
    elif target >= 2 * period and interrupts < target // period - 1:
        raise ValueError("Insufficient serviced SysTick interrupts")
    if row["kind"] in ("dwt_wrap", "long") and row["dwt_wraps"] < 1:
        raise ValueError("DWT rollover not exercised")
    if row["kind"] == "long" and lower <= 0xffffffff:
        raise ValueError("Long interval did not exceed 32-bit cycle range")
    row["serviced_interrupts"] = interrupts


def validate_sample(raw: dict[str, str], index: int, frequency: int, period: int,
                    tolerance: int) -> dict:
    """Recompute counter agreement without trusting firmware PASS labels.

    :param raw:         Raw record fields.
    :param index:       Required sequence index.
    :param frequency:   Reported core frequency.
    :param period:      SysTick period in core cycles.
    :param tolerance:   Fixed sampling tolerance in cycles.
    :returns:           Raw values and derived interval bounds/deltas.
    """
    row = {key: value if key in ("kind", "status") else int(value)
           for key, value in raw.items()}
    if any(value < 0 for value in row.values() if isinstance(value, int)):
        raise ValueError("Negative timer field")
    if (row["index"] != index or (row["kind"], row["target_us"]) != CASES[index]
            or row["status"] != "PASS"):
        raise ValueError(f"Unexpected or failed sample {index}")
    start_lo, start_hi, end_lo, end_hi = (
        row[key] for key in ("dwt_start_lo", "dwt_start_hi", "dwt_end_lo", "dwt_end_hi"))
    if not start_lo <= start_hi <= end_lo <= end_hi:
        raise ValueError("Non-monotonic DWT brackets")
    if max(start_hi - start_lo, end_hi - end_lo) >= period // 4:
        raise ValueError("Sampling uncertainty is too large")
    lower, upper = end_lo - start_hi, end_hi - start_lo
    validate_coverage(row, frequency * row["target_us"] // 1000000, period, (lower, upper))
    for name in ("systick", "cpu"):
        delta = row[f"{name}_end"] - row[f"{name}_start"]
        if delta < 0 or delta + tolerance < lower or delta > upper + tolerance:
            raise ValueError(f"{name} disagrees with DWT in sample {index}")
        row[f"{name}_cycles"] = delta
    row.update(dwt_lower_cycles=lower, dwt_upper_cycles=upper,
               sampling_uncertainty_cycles=upper - lower)
    return row


def parse_boot(text: str, manifest: dict) -> dict:
    """Validate all diagnostic cases and return a complete, auditable boot result.

    :param text:        Complete UART boot, including application termination.
    :param manifest:    Expected firmware identity and constants.
    :returns:           Validated configuration and samples.
    """
    if "program terminating..." not in text or "TIMER error" in text:
        raise ValueError("Incomplete or failed timer diagnostic")
    if single(text, "build")["id"] != manifest["build_id"]:
        raise ValueError("Wrong timer firmware build")
    config = {key: int(value) for key, value in single(text, "config").items()}
    expected = {"version": 1, "clock_hz": 400000000, "period_cycles": 400000,
                "tolerance_cycles": 32, "expected_samples": len(CASES)}
    if any(config.get(key) != value for key, value in expected.items()):
        raise ValueError("Unexpected timer configuration")
    if (config["systick_ctrl"] & 7) != 7 or (config["dwt_ctrl"] & 1) == 0:
        raise ValueError("Counters are not enabled on the core clock")
    if config["dwt_ctrl"] & ((1 << 25) | (1 << 23)):
        raise ValueError("DWT cycle counting unavailable or disabled in secure state")
    summary = single(text, "summary")
    raw = records(text, "sample")
    if summary != {"count": str(len(CASES)), "status": "PASS"} or len(raw) != len(CASES):
        raise ValueError("Missing samples or failed summary")
    samples = [validate_sample(row, index, config["clock_hz"], config["period_cycles"],
                               config["tolerance_cycles"]) for index, row in enumerate(raw)]
    return {"build_id": manifest["build_id"], "status": "PASS", "config": config,
            "samples": samples,
            "scope": "SysTick and production CPU TOTAL versus DWT; "
                     "not independent clock calibration"}


def write_results(boots: list[dict], directory: Path):
    """Write raw and derived records for the selected complete captures.

    :param boots:       Validated boot records with source-log identities.
    :param directory:   Existing bundle directory.
    """
    rows = [{"boot": index, "source_log": boot["source_log"], **sample}
            for index, boot in enumerate(boots) for sample in boot["samples"]]
    if not rows:
        raise ValueError("No validated timer samples")
    (directory / "results.json").write_text(json.dumps({"boots": boots}, indent=2) + "\n",
                                          encoding="utf-8")
    with (directory / "results.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
