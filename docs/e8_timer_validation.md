<!--
SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates <open-source-office@arm.com>
SPDX-License-Identifier: Apache-2.0
-->

# E8 independent timer validation

This standalone M55-HP firmware compares the production Alif SysTick-derived cycle
counter and the actual HAL `CPU TOTAL` reporting path against the independent DWT
CYCCNT hardware counter. Both ET and TFLM benchmarks use that same production timer.
The diagnostic does not load a model or replace any archived benchmark firmware/results.

**Status: physical E8 validation passed on 18 September 2026.** All three returned boots,
72 samples and 144 production-counter comparisons pass independent host recomputation.
Every count falls inside the DWT endpoint bounds without needing the extra 32-cycle
allowance. This closes the timer-validation item for the current SRAM comparison;
no timing correction or inference recollection is indicated by this check.

The available Corstone FVP does not pass the independent-counter comparison. Its
separate limitation remains documented below; the physical-board result is authoritative
for this E8 check.

## Physical E8 results — 18 September 2026

The returned manifest matches both the frozen local bundle and shipped tar byte for
byte. All raw UART boots reparse successfully; every supplied JSON/CSV field is
reproduced, including the source-log checksum. There is one log, three complete boots
and no excluded attempts. The firmware reports 400 MHz, a 400,000-cycle SysTick period,
SysTick CTRL `0x7` and DWT CTRL `0x80000001`.

| Check | Samples across three boots | Outcome |
| --- | ---: | --- |
| Zero-wait overhead | 9 | Both counters inside DWT bounds |
| 100 µs, 900 µs, 1.1 ms, 10 ms, 100 ms, 1 s | 54 | Both counters at DWT bracket midpoint |
| Forced DWT 32-bit rollover, 10 ms | 3 | One rollover and 10 serviced SysTick interrupts each |
| Pending SysTick rollover, interrupts masked for 250 µs | 3 | Pending changes 0 → 1; no ISR servicing during interval |
| Long interval, 12 s | 3 | One DWT rollover and exactly 12,000 serviced SysTick interrupts each |

The elapsed-time bracket is 240 cycles wide (0.60 µs at the reported clock) in 69
samples. The first zero-wait sample of each boot has a wider 391-cycle bracket
(0.9775 µs). All 144 production-counter comparisons are inside the unexpanded brackets.
The configured 32-cycle tolerance is never needed.

Only the first zero-wait sample of each boot differs from the bracket midpoint:
SysTick is +40.5 cycles and HAL `CPU TOTAL` is +6.5 cycles. All remaining samples
coincide with the midpoint for both counters. These are sampling residuals, not known
true counter errors: sequential reads and unequal endpoint windows mean the midpoint
is not an exact simultaneous observation.

The long intervals demonstrate that neither the software tick accumulation nor the
HAL reporting path truncates at 32 bits:

| Boot | SysTick elapsed cycles | CPU TOTAL elapsed cycles | DWT allowed interval, cycles |
| --- | ---: | ---: | --- |
| 1 | 4,800,000,428 | 4,800,000,428 | 4,800,000,308–4,800,000,548 |
| 2 | 4,800,000,434 | 4,800,000,434 | 4,800,000,314–4,800,000,554 |
| 3 | 4,800,000,432 | 4,800,000,432 | 4,800,000,312–4,800,000,552 |

There is no evidence of lost ticks or accumulating drift over these intervals.
DWT and SysTick still share the CPU clock: this validates cycle accounting, not an
independent calibration of 400 MHz or a measurement of inference cache behavior.
The benchmark firmware and reported ET/TFLM performance numbers remain unchanged.

Returned archive:
`build-artifacts/build-e8-timer-validation-artifacts-v1-results-20260918-150716.tar.gz`

SHA256: `70120cd4c52f858e48600e6ee861203980912c63e2be61ad6736f57197fe9904`

The extracted verification copy is under `build-artifacts/collected-2026-09-18-timer/`.
The [JSON audit](results/e8-timer-validation-2026-09-18.json) records firmware/source
identities, archive/log checksums, all endpoint measurements and derived residuals.
The [CSV](results/e8-timer-validation-2026-09-18.csv) has one row per measured interval.
Raw logs and the shipped diagnostic package are preserved unchanged.

## What it checks

Each reset runs 24 cases:

- Three each at 0, 100, 900 and 1,100 microseconds, then 10, 100 and 1,000 milliseconds.
- One 10 ms interval with CYCCNT deliberately positioned just before its 32-bit wrap.
- One 250 microsecond interval with interrupts temporarily masked across a single
  SysTick rollover, exercising pending-interrupt accounting. Masking lasts less than
  one 1 ms SysTick period; interrupts are then restored.
- One 12-second interval, exceeding 2^32 cycles at 400 MHz, with normal SysTick servicing.

The DWT counter is extended in software by frequent polling. Each endpoint reads DWT,
then the production counters, then DWT again. For an elapsed production count `S`, the
independent expected range is:

```text
lower = end_DWT_before - start_DWT_after
upper = end_DWT_after  - start_DWT_before
lower - 32 <= S <= upper + 32
```

The 32-cycle allowance is fixed, not a percentage that could hide accumulating drift.
Endpoint windows must each remain below a quarter of the SysTick period. The firmware
and host independently verify bounds, monotonicity, required durations, interrupt
servicing and rollover coverage. Raw endpoint counters and sampling uncertainty are
retained. Printing occurs after each interval, outside measurement.

No debugger should halt the CPU during this check. If DWT is unavailable or secure-state
counting cannot be enabled, the diagnostic fails explicitly rather than accepting a
substitute counter. The production SysTick algorithm still assumes interrupts are
serviced at least once per tick; deliberately losing multiple ticks is outside its
supported operating conditions.

DWT and SysTick share the CPU clock. Agreement validates cycle accounting and timer
rollover behavior, **not an independent calibration of the reported 400 MHz clock**.
The waiting workload exercises the shared timer; it is not a new inference benchmark.

## Copy and run on the Mac

Copy these files to `/Users/rja/alif/`:

```text
build-e8-timer-validation-artifacts-v1.tar.gz
build-e8-timer-validation-artifacts-v1.tar.gz.sha256
```

Then run:

```sh
cd /Users/rja/alif
shasum -a 256 -c build-e8-timer-validation-artifacts-v1.tar.gz.sha256
tar -xzf build-e8-timer-validation-artifacts-v1.tar.gz
cd build-e8-timer-validation-artifacts-v1
python3 run.py verify
python3 run.py run
```

The packaged script uses `/Users/rja/app-release-exec-macos` and
`/dev/cu.usbmodem0012192765291` by default. Override them with `--tools` and `--port`
if needed. It preserves the installed SE Tools DEVICE configuration, programs M55-HP
at `0x80008000`, opens the serial port at 115200 8N1, and validates each complete boot.
PySerial 3.5 is required for capture; if missing, install it in your Python environment.

Follow the script's switch prompts: SW4 to SE for programming, then U4 for capture.
Reset three times, waiting for each `TIMER summary ... status=PASS` and validated-boot
message before the next reset. A boot takes about 16 seconds plus UART printing.
The final interval is quiet for 12 seconds; wait for its completion.

After all three boots pass:

```sh
python3 run.py collect
```

Copy the timestamped `build-e8-timer-validation-artifacts-v1-results-*.tar.gz` archive
that it prints back to the MLEK host's `build-artifacts/` directory. It contains the
manifest, raw UART log, derived CSV and JSON; it does not copy the firmware back.

To resume capture without programming again:

```sh
python3 run.py capture
```

To reparse a specific completed log, avoiding accidental mixing of attempts:

```sh
python3 run.py summarize --logs logs/timer-YYYYMMDD-HHMMSS-ffffff.log
```

Failed or interrupted captures remain on disk. Do not edit away failing records.
Archive those raw logs separately if a run fails, so the failure can be investigated.
Reflash a previous benchmark package when you want to run inference again.

## Local build and validation

The builder reads the existing E8 TFLM latency build's compilation/link commands and
links a replacement MainLoop in a new output directory. It reuses the existing E8
startup, HAL and production timer objects; the inference-runner archive is excluded.
It does not reconfigure or overwrite the benchmark build. All reused linked inputs
are hashed before and after the diagnostic build.

Local checks on 18 September 2026:

- All 39 tests under `tests/py` pass, including production SysTick rollover fixtures and
  new rejection cases for counter drift, missing ticks and incorrect capture identities.
- The three new Python tools and timer-parser tests pass PyLint 3.3.8 at 10/10;
  diagnostic C++ and headers pass the repository's clang-format check.
- The E8 image compiles, links and places its MRAM payload at `0x80008000`. The map
  retains the existing production timer and HAL objects. The existing linker layout
  emits its usual RWX segment warning; no linker configuration was changed.
- An extracted tar passes checksum verification, replay of three synthetic boots
  (72 samples), CSV/JSON generation and result collection. An incomplete capture is
  rejected without replacing successful results. These synthetic records are not
  included as board results.
- Cppcheck's hardware-header analysis reports an always-false DWT progress test and
  CMSIS header diagnostics. The emitted M55 instructions were reviewed: they perform
  two separate volatile CYCCNT loads around the delay and compare the observed values.
  This is a reviewed static-analysis limitation, not a clean Cppcheck result.

The shipped bundle records these pre-collection checks in `validation/local-checks.json`.
Its original manifest correctly retains the build-time status `hardware_validation=pending`;
the dated result audit above records the subsequent physical pass. No benchmark model
or inference firmware is rebuilt by this diagnostic.

```sh
python3 scripts/py/build_alif_timer_validation.py \
  --base-build build-e8-tflm-tiny-oz-latency \
  --bundle-name build-e8-timer-validation-artifacts-v1
```

The optional simulator run compiles the actual production `timer_alif.c` and `hal_pmu.c`
against standard CMSIS M55 startup/device headers. It runs the same 24-case diagnostic,
including the long interval, and feeds the result through the same host validator.
Its reported 400 MHz is a configured test value, not a board clock observation.
On the available FVP version, DWT elapsed values disagree substantially with SysTick,
including intervals without interrupts. Setting `core_clk.mul=400000000` and
`cpu0.min_sync_level=3` did not resolve the discrepancy. Both attempts are retained as
development evidence; no simulator pass is claimed. The host validator rejects these
records. Do not loosen the board tolerance or rescale DWT to fit the simulator.
The optional `--fvp` build check therefore fails on this model and is omitted above.
Exploratory simulator artifacts are preserved locally under
`build-artifacts/timer-validation-development-v1/validation/`.

The bundle includes its ELF, map, MRAM image, source, commands, SHA256 inventory,
manifest and simulator validation evidence when requested. Use a new `--bundle-name`
for another build; the builder refuses to overwrite an existing package directory.
