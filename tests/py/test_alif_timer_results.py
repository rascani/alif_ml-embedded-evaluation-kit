# SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates
# <open-source-office@arm.com>
# SPDX-License-Identifier: Apache-2.0
"""Reject incorrect counters, rollover coverage and stale timer firmware captures."""

import copy
import importlib
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/py"))
results = importlib.import_module("alif_timer_results")


def sample(index: int) -> dict[str, str]:
    """Construct a physically consistent bracketed counter interval.

    :param index:   Diagnostic case index.
    :returns:       Raw sample fields.
    """
    kind, duration = results.CASES[index]
    cycles = duration * 400 + 200
    start = 0xffff0000 if kind == "dwt_wrap" else 1000
    fields = {
        "index": index, "kind": kind, "target_us": duration, "dwt_start_lo": start,
        "dwt_start_hi": start + 100, "dwt_end_lo": start + cycles + 100,
        "dwt_end_hi": start + cycles + 200, "systick_start": 8000000000,
        "systick_end": 8000000000 + cycles + 100, "cpu_start": 500,
        "cpu_end": 500 + cycles + 100, "irq_start": 20000,
        "irq_end": 20000 + cycles // 400000, "pending_start": 0,
        "pending_end": int(kind == "pending"),
        "dwt_wraps": int(kind in ("dwt_wrap", "long")), "status": "PASS",
    }
    return {key: str(value) for key, value in fields.items()}


def boot(samples: list[dict[str, str]]) -> str:
    """Render a complete synthetic capture to exercise protocol validation.

    :param samples: Raw counter samples.
    :returns:       UART text.
    """
    lines = ["TIMER build id=test-timer",
             "TIMER config version=1 clock_hz=400000000 period_cycles=400000 "
             "tolerance_cycles=32 expected_samples=24 systick_ctrl=7 dwt_ctrl=1"]
    lines += ["TIMER sample " + " ".join(f"{key}={value}" for key, value in row.items())
              for row in samples]
    return "\n".join(lines + ["TIMER summary count=24 status=PASS", "program terminating..."])


class TimerResultsTest(unittest.TestCase):
    """Exercise valid intervals and failures that a PASS label must not hide."""

    def test_full_capture_with_64_bit_counts(self):
        """Accept all cases with explicit bounds and independently derive deltas."""
        result = results.parse_boot(boot([sample(index) for index in range(24)]),
                                    {"build_id": "test-timer"})
        self.assertEqual(len(result["samples"]), 24)
        self.assertGreater(result["samples"][-1]["systick_cycles"], 0xffffffff)
        self.assertEqual(result["samples"][0]["sampling_uncertainty_cycles"], 200)

    def test_counter_disagreement_even_with_pass_labels(self):
        """Reject lost/extra ticks, drift and non-monotonic production counters."""
        for key, delta in (("systick_end", 400000), ("cpu_end", -400000),
                           ("systick_end", 1000), ("cpu_end", -10000000000)):
            with self.subTest(key=key, delta=delta):
                rows = [sample(index) for index in range(24)]
                rows[15][key] = str(int(rows[15][key]) + delta)
                with self.assertRaises(ValueError):
                    results.parse_boot(boot(rows), {"build_id": "test-timer"})

    def test_sampling_bounds(self):
        """Accept fixed tolerance at its boundary, reject one cycle beyond it."""
        raw = sample(0)
        raw["systick_end"] = str(int(raw["systick_start"]) + 200 - 32)
        results.validate_sample(raw, 0, 400000000, 400000, 32)
        raw["systick_end"] = str(int(raw["systick_end"]) - 1)
        with self.assertRaises(ValueError):
            results.validate_sample(raw, 0, 400000000, 400000, 32)

    def test_rollover_and_interrupt_cases_are_required(self):
        """Reject absent rollover, excessive masking and insufficient ISR servicing."""
        for index, key, value in ((21, "dwt_wraps", "0"), (22, "pending_end", "0"),
                                  (22, "irq_end", "20001"), (23, "irq_end", "20000"),
                                  (23, "target_us", "1000000")):
            with self.subTest(index=index, key=key):
                rows = [sample(number) for number in range(24)]
                rows[index][key] = value
                with self.assertRaises(ValueError):
                    results.parse_boot(boot(rows), {"build_id": "test-timer"})

    def test_identity_completeness_and_uncertainty(self):
        """Reject stale, incomplete, duplicate or excessively broad measurements."""
        rows = [sample(index) for index in range(24)]
        valid = boot(rows)
        bad = copy.deepcopy(rows)
        bad[0]["dwt_start_hi"] = "200000"
        texts = [valid.replace("test-timer", "wrong-build"),
                 valid.replace("program terminating...", ""), boot(rows[:-1]),
                 valid.replace("index=0", "index=0 index=0"), boot(bad),
                 valid.replace("tolerance_cycles=32", "tolerance_cycles=400000"),
                 valid.replace("systick_ctrl=7", "systick_ctrl=3")]
        for text in texts:
            with self.subTest(text=text[:80]):
                with self.assertRaises(ValueError):
                    results.parse_boot(text, {"build_id": "test-timer"})


if __name__ == "__main__":
    unittest.main()
