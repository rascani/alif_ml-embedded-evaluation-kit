# SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates
# <open-source-office@arm.com>
# SPDX-License-Identifier: Apache-2.0
"""Exercise the production Alif timer with interrupting simulated registers."""

from pathlib import Path
import subprocess
import tempfile
import unittest


class AlifTimerTest(unittest.TestCase):
    """Compile the real C timer against a small CMSIS register fixture."""

    def test_rollover_and_elapsed_cycles(self):
        """Check serviced/pending wraps, monotonicity, and multi-tick deltas."""
        root = Path(__file__).resolve().parents[2]
        fixture = root / "tests/hal/alif"
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "timer-test"
            subprocess.run(
                [
                    "cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                    "-DCPU_PROFILE_ENABLED=1",
                    f"-I{fixture / 'stubs'}",
                    f"-I{root / 'source/hal/source/platform/alif/include'}",
                    "-I" + str(root / "source/hal/source/components/platform_pmu/include"),
                    str(fixture / "timer_test.c"), "-o", str(executable),
                ],
                check=True, capture_output=True, text=True, timeout=30,
            )
            result = subprocess.run(
                [str(executable)], check=True, capture_output=True, text=True, timeout=10
            )
            self.assertIn(
                "Alif SysTick rollover and multi-tick counter tests passed", result.stdout
            )


if __name__ == "__main__":
    unittest.main()
