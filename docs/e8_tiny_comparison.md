<!--
SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates <open-source-office@arm.com>
SPDX-License-Identifier: Apache-2.0
-->

# E8 Tiny results: ExecuTorch v3 and TFLM

This report preserves the v3 baseline. The [v4 board report](e8_et_tiny_v4_results.md)
records the validated input-storage improvement and the updated comparison with TFLM.

Both suites completed three E8 boots per model on M55-HP at 400 MHz with CPU-only
execution, GCC 15.2.1 `-O3`, CMSIS-NN 8.0.0, INFO logging, and selected operators.
ExecuTorch also retains primitive selection (zero primitive registrations).
Code and models are in MRAM; inference pools are in SRAM; globals, heap and stack use DTCM.

The returned ET archive validated against the original v3 manifest. All 12 boots,
1,200 measured samples, 36 exact saved-output checks, and reported summaries passed.
Returned CSV/JSON values match recomputation from the raw UART logs. RAM is identical
across each model's three boots. Retained inference heap growth is zero; the first
floating-point summary retains 200 diagnostic bytes per boot, excluded from runtime RAM.

These compare the current exported graphs: ET uses untrained seed-23 weights and
synthetic calibration; TFLM uses trained reference models. They are not matched-weight
runtime comparisons or MLPerf accuracy results. DS-CNN retains two internal DQ-to-Q
pairs. ET output checks establish agreement with its lowered Python reference on the
three supplied inputs per model. Independent hardware timer verification remains pending.

## Latency

Mean and p95 use all 300 measured calls per model. Each boot separately times the first
call, then runs ten warm-ups and 100 measured calls. Input filling and printing are
outside timing. No cache flush occurs between calls. Negative change means lower ET latency.

| Model | TFLM mean (ms) | ET mean (ms) | Change | ET p95 (ms) |
| --- | ---: | ---: | ---: | ---: |
| DS-CNN / KWS | 6.036899 | 6.351929 | +5.22% | 6.357450 |
| ResNet8 / IC | 15.720398 | 15.240949 | -3.05% | 15.260840 |
| MobileNetV1 / VWW | 23.901726 | 21.492134 | -10.08% | 21.513465 |
| Autoencoder / AD | 1.202803 | 1.218062 | +1.27% | 1.219725 |

ET per-boot mean spread is below 0.03% for each model. Full first-call timings,
per-boot statistics, and every measured cycle value are retained in the result JSON.

## Filtered flash

Bytes below are model plus attributed runtime/kernels/registry. Runner, diagnostics,
validation fixtures, platform, adapter, shared C/C++ libraries, merged strings, and linker
padding are excluded. Inline checks in retained runtime code remain included. This is
component attribution; additional excluded support is needed for deployment.

| Model | TFLM model + runtime (B) | ET model + runtime (B) | Change |
| --- | ---: | ---: | ---: |
| DS-CNN / KWS | 148,848 | 117,920 | -20.78% |
| ResNet8 / IC | 193,068 | 159,736 | -17.26% |
| MobileNetV1 / VWW | 428,200 | 338,712 | -20.90% |
| Autoencoder / AD | 308,416 | 324,060 | +5.07% |

The [ET component table](e8_et_tiny.md#recorded-static-footprint-v4) and
[TFLM component table](e8_tflm_tiny_flash.md) retain core, kernels, CMSIS-NN and registry
breakdowns. Full ET MRAM payloads are 350,020 / 397,516 / 650,444 / 552,948 bytes for
KWS / IC / VWW / AD, including the excluded support and saved validation fixtures.

## Accounted inference RAM

TFLM totals are arena inference peak (including persistent runtime/kernel tail) plus
outside persistent model/resolver and initialization heap allocations. ET totals are
method-pool usage (including planned buffers), temporary-pool inference peak, outside
persistent model/initialization allocations, and ELF-attributed runtime/registry globals.
Both exclude unused reservations, general call-stack high water, benchmark/platform
memory and shared C/C++ globals. These are scoped inference costs, not whole-device
RAM peaks or minimum arena reservations. Heap snapshots do not measure transient heap peaks.

| Model | TFLM RAM (B) | ET RAM (B) | Change |
| --- | ---: | ---: | ---: |
| DS-CNN / KWS | 28,136 | 50,462 | +79.35% |
| ResNet8 / IC | 55,816 | 62,872 | +12.64% |
| MobileNetV1 / VWW | 101,560 | 124,116 | +22.21% |
| Autoencoder / AD | 9,876 | 6,944 | -29.69% |

The following ET terms are disjoint and sum to the total above. Planned buffers are
already inside the method pool, so they are added only once.

| Model | Planned (B) | Runtime + inputs (B) | Temp invoke peak (B) | Outside persistent (B) | Runtime static (B) |
| --- | ---: | ---: | ---: | ---: | ---: |
| DS-CNN / KWS | 40,000 | 9,254 | 0 | 860 | 348 |
| ResNet8 / IC | 49,728 | 11,996 | 0 | 860 | 288 |
| MobileNetV1 / VWW | 73,728 | 49,240 | 0 | 860 | 288 |
| Autoencoder / AD | 768 | 5,124 | 0 | 860 | 192 |

ET initialization temporary peaks are 212 / 200 / 212 / 166 bytes for KWS / IC / VWW / AD,
reported separately from the zero inference peaks. Every image still reserves 256 KiB
for the method pool and 64 KiB for the temporary pool in SRAM. TFLM reserves 256 KiB for
its arena; its initialization planner temporarily uses almost the full reservation.
Measured usage provides a starting point for later arena sizing and TCM placement.

## Explanation of the differences

The [delta inspection JSON](results/e8-tiny-delta-analysis-2026-09-16.json) records graph
shapes, weight counts, input-planning metadata, source evidence and byte reconciliations.
Each corresponding convolution/linear has matching input/output shapes and weight counts.
The INT8 weight payloads are identical in size: 22,016 / 77,360 / 208,112 / 264,192 bytes
for KWS / IC / VWW / AD. Values and quantization parameters differ. Smaller ET PTE files
therefore do not demonstrate smaller networks: encoding, metadata, auxiliary constants
and sharing/deduplication also determine model-file size.

The flash deltas below are ET minus TFLM in bytes; negative means ET is smaller.

| Model | Model file | Core | Operators | CMSIS-NN | Registry | Total |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| KWS | -11,136 | +21,156 | -8,768 | -36,548 | +4,368 | -30,928 |
| IC | -2,600 | +21,220 | -26,100 | -29,156 | +3,304 | -33,332 |
| VWW | -65,440 | +21,156 | -12,416 | -36,548 | +3,760 | -89,488 |
| AD | +2,992 | +22,536 | -3,708 | -8,672 | +2,496 | +15,644 |

ET core and registry are larger in every image. The CNN totals become smaller because
the selected Cortex-M operators and their CMSIS-NN dependencies are narrower, and the
serialized models are smaller. TFLM selects operator types but their generic Eval
functions retain numeric alternatives: float reference paths and INT4/INT16 CMSIS-NN
paths remain linked alongside INT8. These alternatives consume flash even though this
benchmark does not execute them. TFLM IC's ADD object contributes 17,012 bytes by itself;
KWS/VWW include a 3,828-byte `arm_depthwise_conv_s4` object. For the FC-only autoencoder,
there is less kernel code to remove, so ET's larger fixed core/registry makes its total
15,644 bytes larger. This is a remaining TFLM numeric-specialization opportunity, not
a consequence of a different CMSIS-NN version or disabling operator selection.

RAM has different causes:

- **KWS:** ET planned storage is 40,000 B versus TFLM's 20,464 B arena head. Each of the
  two DQ/Q pairs materializes a `[1,25,5,64]` FLOAT tensor: 32,000 B. They share offset
  zero at different lifetimes, so their memory is not added together. This explains
  the large planned-buffer pressure; the plan difference contributes 19,536 B of the
  22,326 B total RAM gap. The other 2,790 B is the difference in metadata, staging
  inputs and outside/static storage. Removing DQ/Q should reduce memory and work;
  the exact result requires re-exporting and measuring the new plan.
- **IC and VWW:** planned sizes already match TFLM's arena head exactly: 49,728 and
  73,728 B. The ET adapter nonetheless allocates a separate staging input buffer even
  though each PTE input has allocation metadata. ET `Method::set_input()` copies that
  buffer into the planned input on every timed `RunInference()`. The staging buffers
  consume 3,072 and 27,648 B respectively, plus a four-byte pointer allocation. This is
  an adapter inefficiency, not a required property of ExecuTorch. VWW's staging input
  is larger than its entire 22,556 B RAM disadvantage; other ET state offsets part of it.
- **AD:** both planned/head sizes are 768 B. TFLM stores 6,688 B of precomputed FC kernel
  sums in persistent RAM; the ET export stores the corresponding sums as model constants
  in MRAM. ET has more metadata/other storage, so the net saving is 2,932 B. This is a
  concrete RAM-versus-ROM tradeoff, not a smaller activation plan.

For reference, the ET method metadata costs are 8,760 / 8,920 / 21,588 / 4,480 B, plus
staging inputs of 494 / 3,076 / 27,652 / 644 B including their pointer allocations.
TFLM's persistent arena tails are 6,884 / 5,300 / 27,044 / 8,500 B. These categories
are not identical: TFLM allocates convolution per-channel multipliers/shifts in RAM,
while ET consumes serialized constants. TFLM's raw convolution quantization-array
payload alone is 4,608 / 2,688 / 21,888 / 0 B; allocator bookkeeping/alignment is additional.

Latency is less completely explained than bytes. KWS's four extra conversion calls
are a concrete source of extra work and likely contribute to its 5.22% slowdown.
Input copying inside ET's timed invocation also adds work in all four models. IC is
3.05% faster and VWW 10.08% faster, while AD is 1.27% slower, but current measurements do
not isolate those differences. Corresponding compute shapes match and both paths use
CMSIS-NN 8.0.0; different quantization parameters, wrapper/dispatch work, implementation
branches and cache/code/data placement still matter. Do not attribute the whole delta
to interpreter overhead or weight values without per-operator measurements. Differences
exceed the observed within-configuration boot-to-boot variation, which does not rule out
systematic code-placement or configuration effects.

The most direct next experiments are to remove ET's redundant input staging/copy,
rerun the cleaned DS-CNN export, specialize TFLM registrations by numeric type, and then
collect per-operator timings on matched model/quantization pairs. The frozen SRAM results
remain the baseline; none of those changes has been applied to these binaries.

## Saved records

- [ET JSON: provenance, hashes, aggregates and all samples](results/e8-et-tiny-2026-09-16-v3.json)
- [ET CSV: per-model latency, flash and RAM breakdown](results/e8-et-tiny-2026-09-16-v3.csv)
- [Comparison CSV](results/e8-tiny-comparison-2026-09-16.csv)
- [TFLM JSON](results/e8-tflm-tiny-2026-09-16.json)

The original returned archive is `build-artifacts/e8-et-tiny-results-v3.tar.gz`, SHA256
`f95f62de88950e6ae0d2d63f600e5861bb6683037fc13b633342230e0b3a4ec4`.
Raw logs and recomputed per-boot CSV/JSON are under `build-artifacts/e8-et-tiny-results-v3/`.
The shipped firmware bundle and its manifest remain unchanged; hardware validation is
recorded here and in the new result JSON.

The subsequent [v4 adapter update](e8_et_tiny.md#v4-input-storage-change) removes input
staging and copying. It uses the same PTEs and filtered runtime flash sizes. Its E8 run
now validates all 1,200 measured calls and 36 output checks; the [v4 report](e8_et_tiny_v4_results.md)
records the new results, while measurements in this report remain the frozen v3 baseline.
