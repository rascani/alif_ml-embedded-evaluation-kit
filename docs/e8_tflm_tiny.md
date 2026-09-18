<!--
SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates <open-source-office@arm.com>
SPDX-License-Identifier: Apache-2.0
-->

# Four TFLM Tiny benchmarks on the E8

The latest artifacts are [v3 INT8 size/latency builds](e8_tflm_int8_registration_results.md).
The instructions and measurements below describe the earlier reference experiment.

This package contains one CPU-only M55-HP image for each original MLPerf Tiny workload:
`kws` (DS-CNN keyword spotting), `ic` (CIFAR-10 ResNet image classification), `vww`
(96×96 visual wake words), and `ad` (ToyCar anomaly detection). All four are the INT8
reference TFLite models from MLCommons Tiny commit
`4addd0fa08d216e20637637874e084895f289da4`. Exact paths and SHA256 hashes are in `manifest.json`.

Firmware uses GCC 15.2.1, CMSIS-NN 8.0.0, model-specific TFLM operator selection, internal
MRAM for code/model, and a 256 KiB SRAM arena. Logging stays enabled. The benchmark uses
the existing deterministic synthetic input, one separately timed first invocation,
10 warm-ups, and 100 measured invocations. This is a latency/memory experiment, not an
official MLPerf accuracy or end-to-end preprocessing measurement. Board results were
collected on the Mac on 2026-09-16; native timings and pointer sizes are kept separate.
The arena starts at `0x02000000`; persistent heap allocations and the model wrapper live
in DTCM, with the wrapper on the stack.

## Run on the Mac

Copy `build-e8-tflm-tiny-artifacts.tar.gz` and its `.sha256` file to `/Users/rja/alif/`.
Extract the archive and enter its directory:

```bash
cd /Users/rja/alif
shasum -a 256 -c build-e8-tflm-tiny-artifacts.tar.gz.sha256
tar -xzf build-e8-tflm-tiny-artifacts.tar.gz
cd build-e8-tflm-tiny-artifacts
/usr/bin/python3 run.py run all
```

`run.py` verifies all packaged checksums. For each model it prompts you to close other
serial readers and set **SW4 to SE**, builds the SE Tools package, and programs the image.
It preserves the installed `DEVICE` configuration and boots M55-HP at `0x80008000`.
It then opens capture and instructs you to set **SW4 to U4** and reset three times, waiting
for completion between resets. Capture stops automatically after three validated boots,
then the script proceeds to the next model. Leave the board connected to PRG USB J3.

Defaults match the working Mac setup: SE Tools in `~/app-release-exec-macos`, port
`/dev/cu.usbmodem0012192765291`, 115200 8N1, no flow control. Override with `--tools` or
`--port` if needed. The host scripts support Python 3.9 and newer. Capture uses pyserial,
already installed for the earlier reader;
if using another Python environment, install it with `python3 -m pip install pyserial==3.5`.

Other useful commands, all included in the package:

```bash
/usr/bin/python3 run.py list
/usr/bin/python3 run.py run kws
/usr/bin/python3 run.py flash vww
/usr/bin/python3 run.py capture vww
/usr/bin/python3 run.py summarize
```

`--boots` defaults to 3. `--timeout` defaults to 600 seconds per model. Ctrl-C closes
capture and preserves received bytes. A new timestamped raw file is created for each
capture in `logs/`. The script rejects a wrong model/hash, missing samples, mismatched
summaries, incorrect timer units, incomplete boots, or inconsistent memory accounting.
`summarize` combines complete logs into `results.csv` and `results.json`; JSON also retains
every cycle sample. `run all` writes those same results files after finishing all models.
Single-model runs write files such as `kws-results.csv` and `kws-results.json`.
Move interrupted/incomplete logs out of `logs/` before summarizing.

## Metrics

The [ET/TFLM board comparison](e8_tiny_comparison.md) records the completed SRAM runs
for both suites, including the different weight sources and scoped memory definitions.

`flash.csv` is available before board execution. UART results add latency and RAM columns.

For model/runtime comparisons excluding harness and platform ownership, see the
[filtered flash analysis](e8_tflm_tiny_flash.md). The saved board summary now includes
`flash_filtered_runtime_bytes` and `flash_filtered_model_runtime_bytes` in addition to
the original complete-image metrics below. Shared C/C++ support is reported separately.

The packaged GCC images have these exact MRAM payload sizes, in bytes:

| Model | Model | Runtime + runner/platform | Total |
| --- | ---: | ---: | ---: |
| KWS | 53,936 | 307,444 | 361,380 |
| Image classification | 98,496 | 306,900 | 405,396 |
| Visual wake words | 333,288 | 307,444 | 640,732 |
| Anomaly detection | 276,976 | 239,572 | 516,548 |

| Metric | Definition |
| --- | --- |
| `first_us` | First invocation after initialization, excluded from measured statistics |
| `mean_us`, `median_us`, `min_us`, `max_us`, `p95_us` | 100 measured invocations, converted using the reported core clock |
| `flash_total_bytes` | Exact application MRAM payload, including model, runtime, kernels, runner, diagnostics, platform code and initialized data |
| `flash_model_bytes` | Exact embedded `.tflite` size |
| `flash_non_model_bytes` | Total payload minus model; includes shared C/C++ and platform overhead, not just TFLM |
| `arena_head_bytes` | Planned activation and scratch space after inference |
| `arena_persistent_bytes` | Arena tail: TFLM metadata, kernel persistent buffers, allocator/planner objects and alignment |
| `arena_invoke_peak_bytes` | Maximum simultaneous head/temp + tail during the inference batch |
| `arena_init_peak_bytes` | Peak head/temp + tail during initialization, including temporary planning workspace |
| `outside_persistent_bytes` | Model/resolver wrapper object plus retained libc heap growth during model initialization |
| `ram_inference_peak_bytes` | Inference arena peak + outside persistent bytes |
| `ram_lifecycle_arena_plus_persistent_bytes` | Larger of initialization/inference arena peaks + outside persistent bytes |

Use `ram_inference_peak_bytes` as the primary inference RAM cost. The greedy planner can
temporarily reserve all available arena space during initialization; `arena_init_peak_bytes`
then reflects that workspace reservation, not the smallest arena the model can use.
We retain that value separately rather than claiming it is a minimum allocation requirement.

Persistent TFLM and kernel buffers are already in the arena tail. **Do not add the tail
again to an arena peak.** The interpreter object is heap-allocated in this integration;
`outside_interpreter_object_bytes` is informational and already included in the heap delta.
The heap delta includes libc allocator bookkeeping and any retained allocation caused by
model initialization/logging. The model wrapper size includes the selected operator resolver.

These RAM costs exclude ordinary call-stack high-water, platform static RAM, general
stdio state allocated before model initialization, and the benchmark sample vectors.
They measure arena peaks plus persistent runtime/wrapper storage, rather than total-device
RAM high-water. Whole-firmware static sections and heap/stack reservations are included
in each model's `sections.json` and linker map. A 256 KiB reserved arena is a capacity,
not an assertion that the model uses all 256 KiB.

The audit allocator reserves its extra tracking fields in the arena. `arena_audit_overhead_bytes`
is subtracted once from arena cost figures to exclude the tracking storage;
`arena_raw_peak_bytes` includes it. Padding preserves ordinary allocator alignment. Native
tests confirm ordinary and audited inference arena sizes match after this subtraction,
and their outputs match. Initialization workspace may grow to consume freed capacity.
`invoke_allocation_calls` reports
whether the audited allocation methods ran during inference; zero means there were no added
tracking callbacks in timed model invocations. Memory logging occurs after timing.

The application payload includes benchmark and memory-diagnostic code. It excludes SE Tools
device configuration, boot-package metadata, and final 16-byte programming padding. Keep
these definitions unchanged when comparing to ExecuTorch later.

## Board results: 2026-09-16

All four images completed three boots on M55-HP at 400 MHz. The 1,200 measured samples
reproduce every firmware summary and the returned CSV/JSON. The returned manifest matches
the packaged firmware manifest. Each boot contains one first invocation, 10 warm-ups and
100 measured invocations; the table pools the 300 measured samples for each model.
P95 uses the nearest-rank convention. First invocations and warm-ups are excluded.

| Model | Mean (ms) | Median (ms) | P95 (ms) | First invocation range (ms) | Boot mean spread |
| --- | ---: | ---: | ---: | ---: | ---: |
| KWS | 6.036899 | 6.036869 | 6.040515 | 6.142700–6.148770 | 0.0300% |
| Image classification | 15.720398 | 15.720126 | 15.743305 | 15.718815–15.753600 | 0.0305% |
| Visual wake words | 23.901726 | 23.901618 | 23.919330 | 23.945010–23.973120 | 0.0137% |
| Anomaly detection | 1.202803 | 1.202830 | 1.203115 | 1.208130–1.208333 | 0.0026% |

Boot mean spread is `(maximum boot mean - minimum boot mean) / pooled mean`.
All memory figures below are bytes and were identical across each model's three boots.

| Model | Arena activation/scratch | Arena persistent | Arena inference peak | Outside persistent | Total inference RAM |
| --- | ---: | ---: | ---: | ---: | ---: |
| KWS | 20,464 | 6,884 | 27,348 | 788 | 28,136 |
| Image classification | 49,728 | 5,300 | 55,028 | 788 | 55,816 |
| Visual wake words | 73,728 | 27,044 | 100,772 | 788 | 101,560 |
| Anomaly detection | 768 | 8,500 | 9,268 | 608 | 9,876 |

Outside persistent storage is a 292-byte model/resolver object (112 bytes for anomaly
detection) plus 496 bytes of retained initialization heap growth. The 208-byte interpreter
is included in that heap growth. The arena figures exclude the 32-byte audit overhead.
There were zero allocation callbacks during inference on all 12 boots.

Initialization arena peaks excluding audit storage were 262,100 / 262,108 / 262,104 /
262,112 bytes for KWS / IC / VWW / AD. These reflect the greedy planner's temporary use
of almost the entire 256 KiB reservation, not the minimum capacity needed by each model.
The primary inference RAM figures above retain the scope defined in the Metrics section.

[Summary CSV](results/e8-tflm-tiny-2026-09-16.csv) and
[full records, samples and hashes](results/e8-tflm-tiny-2026-09-16.json) preserve this SRAM
baseline. Raw captures and recomputed per-boot outputs are retained under
`build-artifacts/e8-tflm-tiny-results/`. The original returned archive has SHA256
`683d38fcd3f42f8e811e69aeaa2896be63547896123667d34c9d51b227cd4d87`.
The firmware bundle remains unchanged. Known-input accuracy checks, independent hardware
timer checks, matched ET models and TCM placement experiments remain separate work.

## Reproduce the binaries

From the repository and its prepared `resources_downloaded/env`:

```bash
resources_downloaded/env/bin/python scripts/py/build_tflm_tiny.py \
  --gcc-bin /path/to/arm-gnu-toolchain-15.2.rel1-x86_64-arm-none-eabi/bin
```

The script downloads only pinned model bytes, validates their hashes, runs native model and
allocator tests, builds the explicit E8 runner target for each model, checks embedded bytes,
and packages binaries, ELFs, maps, sections, selected operators, build/test logs, source changes,
host scripts, and checksums. It refuses to overwrite an existing bundle. Use `--bundle-name`
for a new snapshot; existing smoke and benchmark bundles remain independent.

All four native runner/test builds and E8 cross-builds passed. Each native runner completed
111 invocations with no audited allocation callbacks during inference. The packaged scripts
also completed board programming, capture and aggregation for all four models as recorded above.
