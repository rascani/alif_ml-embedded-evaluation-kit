<!--
SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates <open-source-office@arm.com>
SPDX-License-Identifier: Apache-2.0
-->

# E8 independent timer validation

This standalone M55-HP diagnostic compares the production SysTick-derived cycle
counter and the HAL `CPU TOTAL` reporting path against DWT CYCCNT. It reuses the
platform timer used by inference, without loading a model or replacing benchmark
firmware. DWT and SysTick share the CPU clock: agreement validates cycle accounting,
not the absolute accuracy of the reported 400 MHz frequency.

## Recorded physical result

**Passed on the E8 on 18 September 2026:** three boots, 72 samples and 144 counter
comparisons. Every production count falls inside the DWT endpoint bounds without
the configured additional 32-cycle allowance. No timer correction or inference
recollection was indicated. The original measurements remain unchanged.

| Check | Samples across three boots | Outcome |
| --- | ---: | --- |
| Zero-wait overhead | 9 | Both production counters inside DWT bounds |
| 100 µs through 1 s intervals | 54 | Both counters at the bracket midpoint |
| Forced DWT rollover, 10 ms | 3 | One rollover and 10 serviced SysTick interrupts |
| Pending SysTick rollover, interrupts masked for 250 µs | 3 | Pending transition observed without ISR servicing |
| Long interval, 12 s | 3 | One DWT rollover and 12,000 serviced interrupts |

The elapsed-cycle bracket is 240 cycles wide in 69 samples and 391 cycles wide in
the first zero-wait sample of each boot. These are sampling uncertainty bounds, not
known timer errors. The long intervals report approximately 4.8 billion cycles,
exercising the full 64-bit production/HAL reporting path.

The original returned archive is
`build-artifacts/build-e8-timer-validation-artifacts-v1-results-20260918-150716.tar.gz`,
SHA256 `70120cd4c52f858e48600e6ee861203980912c63e2be61ad6736f57197fe9904`.
The detailed JSON/CSV audit and original report are retained in the separate
`build-artifacts/e8-documentation-archive-2026-09-24.tar.gz` evidence archive.
A newly built diagnostic starts with validation pending and requires its own capture.

## What is checked

Each endpoint reads DWT, then production counters, then DWT again. For an elapsed
production count `S`, the accepted interval is:

```text
lower = end_DWT_before - start_DWT_after
upper = end_DWT_after  - start_DWT_before
lower - 32 <= S <= upper + 32
```

The fixed tolerance cannot conceal percentage drift. Endpoint windows must remain
below a quarter of the SysTick period. Firmware and host both check sample identity,
monotonicity, interrupt servicing, rollover coverage and duration. Raw endpoint reads
are retained. Printing occurs outside each interval. Do not halt the CPU with a
debugger during capture. SysTick interrupts must be serviced at least once per
period; masking across multiple periods is outside the supported counter contract.

The available Corstone FVP did not pass the independent-counter comparison. DWT and
SysTick disagreed even without interrupts, and the host validator rejected the runs.
No simulator pass is claimed. Keep board tolerances unchanged; simulator limitations
are separate from the physical result.

## Build and package

Use an existing E8 CPU-only latency build containing its compilation database and
linked platform objects. The builder creates a new diagnostic directory, reuses
startup/HAL/timer objects and verifies that reused inputs remain unchanged.
Put the GCC toolchain on `PATH`; run from the repository root:

```bash
resources_downloaded/env/bin/python scripts/py/build_alif_timer_validation.py \
  --base-build build-e8-tflm-tiny-oz-latency \
  --bundle-name build-e8-timer-validation-new
```

The resulting archive and checksum file are alongside the new bundle directory.
Use a fresh name for each build. The optional `--fvp` check is omitted because the
available model has the counter disagreement described above. The archive contains
firmware, source, build commands, hashes, a manifest and the runnable capture tools.

## Program, capture and collect

On the Mac, install PySerial 3.5 and use the existing Alif SE Tools installation.
Copy the new archive and checksum file, then run:

```bash
cd ~/alif
shasum -a 256 -c build-e8-timer-validation-new.tar.gz.sha256
tar -xzf build-e8-timer-validation-new.tar.gz
cd build-e8-timer-validation-new
python3 run.py verify
python3 run.py run --tools "$HOME/app-release-exec-macos" --port /dev/cu.YOUR_BOARD_PORT
python3 run.py collect
```

Follow SW4 prompts: SE for programming and U4 for capture. Reset three times,
waiting for `TIMER summary ... status=PASS` and host validation each time. A boot
includes a quiet 12-second interval; allow it to finish. `collect` prints a results
archive containing the manifest, raw UART log and derived CSV/JSON for return to
the build host. Preserve failed attempts separately. `run.py capture` resumes
without programming, and `run.py summarize --logs logs/timer-TIMESTAMP.log` reparses
a selected capture. Reflash an inference package afterward to resume model tests.
