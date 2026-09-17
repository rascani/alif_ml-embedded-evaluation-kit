<!--
SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates <open-source-office@arm.com>
SPDX-License-Identifier: Apache-2.0
-->

# E8 CPU benchmark runner

Both frameworks now support a repeatable CPU benchmark. Native execution and tests pass,
and both E8 M55-HP firmware targets build with GCC 15.2.1, CMSIS-NN 8.0.0, logging enabled,
and model-specific operator selection. ET primitive selection remains enabled.
**Both ExecuTorch and TFLM have completed three benchmark boots on the E8.** All 600
measured sample values reproduce their reported summaries. The earlier smoke images for
both frameworks also ran successfully.

The new bundle is `build-artifacts/e8-cpu-benchmark-bringup.tar.gz`, which extracts as
`build-e8-cpu-benchmark-artifacts`. The previous smoke bundle is preserved unchanged.

| Framework | MRAM payload | Model | SRAM pools reserved |
| --- | ---: | --- | ---: |
| ExecuTorch | 275,716 bytes | `smoke-cortex-m.pte`, 3,040 bytes | 64 KiB method + 64 KiB temporary |
| TFLM | 344,436 bytes | `dnn_s_quantized.tflite`, 84,192 bytes | 64 KiB tensor arena |

The models are unchanged and **different networks**. This bundle validates the measurement
workflow; framework performance comparisons require matched Tiny models and reference inputs.

## ExecuTorch board results, 2026-09-16

The user supplied three complete boots from `/Users/rja/alif/logs/et/et-benchmark-uart.log`.
Each reports 111 invocations, 10 warm-ups, 100 measured samples, no delegates, and successful
completion. Recalculating every summary from the 300 supplied sample values matches all
reported statistics exactly. The clock is 400 MHz throughout.

| Boot | First (cycles) | Measured mean (cycles) | First (µs) | Mean (µs) | Median (µs) | p95 (µs) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 11,971 | 4,577.100 | 29.9275 | 11.442750 | 11.37750 | 11.9900 |
| 2 | 12,259 | 4,560.830 | 30.6475 | 11.402075 | 11.47375 | 11.8950 |
| 3 | 12,195 | 4,549.610 | 30.4875 | 11.374025 | 11.31250 | 11.8275 |

The mean range is 0.60% of the pooled mean. Across all measured samples, the minimum is
4,302 cycles (10.755 µs), and the maximum is 4,860 cycles (12.150 µs). Method-pool usage
and peak remain 1,565 bytes before and after each boot's inference batch. Temporary-pool
usage returns to zero, and its lifetime peak remains 166 bytes. These counters do not
measure heap or stack high-water marks.

The sample sequences contain constant and repeating stretches; the log does not establish
their cause or prove that 10 warm-ups yield a stationary timing distribution. The first
invocation is recorded separately and is not part of the measured summaries. These results
confirm the ET board benchmark workflow and repeatability of its mean, without establishing
model accuracy or a performance comparison with TFLM's different smoke network.

[Recorded samples and metadata](results/e8-et-benchmark-2026-09-16.json) are transcribed
from the supplied text; the original raw serial file remains on the Mac. The frozen bundle
and its manifest retain their build-time validation status. Reference-output checks and
independent hardware timer checks over long intervals remain pending.

## TFLM board results, 2026-09-16

The user supplied three complete boots from `/Users/rja/alif/logs/tflm/tflm-benchmark-uart.log`.
Each reports 111 invocations, 10 warm-ups, 100 measured samples, and successful completion.
Recalculating every summary from all 300 sample values matches the reported statistics
exactly. The processor clock is 400 MHz on all three boots.

| Boot | First (cycles) | Measured mean (cycles) | First (µs) | Mean (µs) | Median (µs) | p95 (µs) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 159,310 | 149,671.090 | 398.2750 | 374.177725 | 374.0075 | 376.955 |
| 2 | 158,380 | 149,663.330 | 395.9500 | 374.158325 | 374.2325 | 376.475 |
| 3 | 159,307 | 149,753.430 | 398.2675 | 374.383575 | 374.3000 | 376.895 |

The mean range is 0.060% of the pooled mean. Across all measured samples, the minimum
is 147,902 cycles (369.755 µs), and the maximum is 151,166 cycles (377.915 µs). Each boot
reports 4,160 bytes of arena usage at initialization, within the firmware's reserved
64 KiB SRAM arena. These logs do not report heap or stack high-water marks.

[Recorded TFLM samples and metadata](results/e8-tflm-benchmark-2026-09-16.json) are
transcribed from the supplied text; the original raw serial file remains on the Mac.
The graph has fp32 input `[1, 250]`, output `[1, 12]`, and seven operator occurrences:
quantize, four fully connected layers, softmax, and dequantize.

This completes the programming, boot, capture, and three-reset benchmark workflow for
both frameworks: six successful boots and 600 measured samples. The smoke networks
differ, so these times and arena sizes do not establish relative framework performance.
The next phase is matched Tiny model integration and known-input output validation,
followed by comparable SRAM measurements and the planned TCM experiments.

## What each boot does

1. Initialize the model once.
2. Refill deterministic input and time the first inference separately.
3. Perform 10 additional warm-up inferences.
4. Time 100 measured inferences, refilling the same input before every invocation.
5. Print the first time, all 100 samples in invocation order, and count/min/mean/median/max/p95.

That is **111 invocations per successful boot**. Neither initialization nor the first
inference nor warm-ups contribute to the 100-sample statistics. Median averages the middle
two samples for even counts; p95 uses nearest rank (the 95th sorted sample for 100 samples).

The timed region brackets `Model::RunInference()` with HAL counter reads. It includes
framework adapter work such as ET input registration, runtime execution, interrupt service,
and timestamp read overhead. It excludes input filling, statistics, and runner UART output.
Successful invocations of these smoke models do not log at INFO level; failed invocations
abort the benchmark without printing a successful summary. Counts are not overhead-corrected.

The first time is the first invocation after initialization, **not** a guarantee of cold
caches. Warm-ups and measured invocations reuse the same initialized model. This mode assumes
stateless inference; it does not reset recurrent state. Refilling input also affects caches.

Input `synthetic_v1` supports fp32, int8, and uint8. Float element `j` of input `i` is
`(((j + 13*i) % 17) - 8) / 8`; 8-bit input bytes are `(37*j + 13*i + 11) % 256`.
This is reproducible synthetic data, not an accuracy corpus or a quantization-aware matched
sample across model formats. Other input types fail explicitly. Known-input validation and
equivalent Tiny model preparation remain separate work.

At the default count, sample storage uses 800 bytes of heap; calculating statistics makes
another 800-byte sorted copy after timing. Framework arena reservations, the 64 KiB heap,
and the 32 KiB stack are unchanged. Arena logs do not include this measurement storage.

## Build configuration

Starting from either configured CPU build in [the bring-up guide](e8_cpu_bringup.md):

```bash
export PATH="$PWD/resources_downloaded/env/bin:/home/rja/executorch/examples/arm/arm-scratch/arm-gnu-toolchain-15.2.rel1-x86_64-arm-none-eabi/bin:$PATH"
cmake -S . -B build-e8-et-cpu \
  -Dinference_runner_BENCHMARK_ENABLED=ON \
  -Dinference_runner_WARMUP_COUNT=10 \
  -Dinference_runner_ITERATION_COUNT=100
cmake --build build-e8-et-cpu --target mlek_inference_runner -j8
```

Repeat with `build-e8-tflm-cpu`. Benchmark mode defaults to OFF and accepts 0–1000 warm-ups
and 1–1000 measured iterations. It requires a CPU-only embedded model, INFO-level MLEK
logging, and `CPU_PROFILE_ENABLED=ON` on embedded platforms. Native builds report
`microseconds`; E8 reports `cycles`. Setting `inference_runner_BENCHMARK_ENABLED=OFF`
restores the original one-inference handler.

Build the explicit runner target: building all embedded targets also builds unused Arm-2D
graphics code, which triggers an internal compiler error in this GCC version. No Arm-2D
changes are needed for the inference runner.

The Alif timer now retries a sample if SysTick interrupts or becomes pending between
register reads, and accounts for a pending wrap not yet included in the ISR count.
Simulated-register tests compile the production timer and cover serviced/pending wraps,
monotonicity, multi-tick intervals, and values beyond 32 bits. Interrupts must be serviced
at least once per 1 ms SysTick period. Independent hardware timer validation remains pending; the
existing 400 MHz clock banner gives microseconds as `cycles / 400` for these board settings.

## Copy and run on the Mac

Copy the archive and its `.sha256` sidecar to `/Users/rja/alif/`. In the Mac environment:

```bash
cd /Users/rja/alif
shasum -a 256 -c e8-cpu-benchmark-bringup.tar.gz.sha256
tar -xzf e8-cpu-benchmark-bringup.tar.gz
cd build-e8-cpu-benchmark-artifacts
shasum -a 256 -c SHA256SUMS
```

Stop the UART reader with Ctrl-C and set **SW4 to SE**. To program ET:

```bash
(
set -e
cd /Users/rja/app-release-exec-macos
cp /Users/rja/alif/build-e8-cpu-benchmark-artifacts/et/mram.bin \
  build/images/e8-benchmark-et.bin
cp /Users/rja/alif/build-e8-cpu-benchmark-artifacts/setools/e8-benchmark-et.json \
  build/config/e8-benchmark-et.json
./app-gen-toc -f build/config/e8-benchmark-et.json
./app-write-mram -c /dev/cu.usbmodem0012192765291 -p
)
```

These configs preserve the supplied SE Tools 0.35.000 `DEVICE` entry and boot M55-HP from
MRAM at `0x80008000`, as in the working smoke setup. Then set **SW4 to U4**:

```bash
mkdir -p /Users/rja/alif/logs/et
/usr/bin/python3 /Users/rja/alif/build-e8-cpu-benchmark-artifacts/capture_uart.py \
  --port /dev/cu.usbmodem0012192765291 \
  --output /Users/rja/alif/logs/et/et-benchmark-uart.log
```

Reset after `Listening on ...`. Expect `Total number of inferences: 111`,
`BENCHMARK config version=1 input=synthetic_v1 warmups=10 measured=100`, a separate
`BENCHMARK first` record, 100 `BENCHMARK sample` records with `unit=cycles`, a
`BENCHMARK summary count=100 ... unit=cycles`, and `Inference completed.`.
Allow the entire output to finish before resetting; collect three complete boots.

For TFLM, repeat the programming and capture commands substituting `tflm` for `et` in
image, config, and log paths. Retain the raw logs and bundle checksums. The reader appends,
so use these new benchmark log paths to keep earlier smoke captures distinct.

## Validation recorded with this bundle

- Both native CTest suites pass, including 111 real-model invocations, input restoration,
  failure handling, statistics, and counter validation.
- Native output has exactly 100 ordered samples; a separate calculation agrees with all
  reported statistics. Native times do not estimate E8 performance.
- Eleven Python tests pass, including the production Alif timer register simulation.
- The new Python test passes pylint 3.3.8; new C/C++ files pass clang-format checks.
- Both E8 runner targets link; their payloads contain the expected unchanged model bytes.
  ET retains its three-entry operator registry and no runtime primitive kernels.
- The native ET legacy handler was rebuilt and run with benchmark mode OFF; an invalid
  measured count was rejected at configuration time, then benchmark defaults were restored.

Board execution and three-reset statistics for both frameworks are now recorded above.
Reference-output accuracy validation, matched Tiny model comparisons, and independent
hardware timer checks over long intervals remain pending.
