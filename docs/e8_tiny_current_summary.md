<!--
SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates <open-source-office@arm.com>
SPDX-License-Identifier: Apache-2.0
-->

# ExecuTorch vs TFLM — primary SRAM comparison

**17 September 2026 · ExecuTorch v8 · TFLM v3 · SRAM inference pools · Cortex-M55-HP · CPU-only, 400 MHz**

GCC 15.2.1 uses `-Oz` for runtime/operator wrappers and `-O3` for CMSIS-NN 8.0.0,
with function/data sections. Both frameworks select model-specific operators;
TFLM uses compatible INT8 registrations and ET has zero selected primitive registrations.
Code/models use MRAM; inference pools use SRAM; globals/heap/stack use DTCM.

SRAM inference pools are the supported configuration for these comparisons.

The new ET v8 collection confirms the integer-pooling RAM savings on E8. TFLM v3
uses its previous measured SRAM collection. See the
[integer-pooling analysis](e8_et_tiny_v8_results.md) for deltas from ET v6.

**Flash columns use the separate logging-disabled size builds. Latency, cycles and RAM
come from the logging-enabled board builds.** No latency or RAM is claimed for the silent
builds. KiB = 1,024 bytes; bold marks the lower value in each pair.

| Model | Framework | Mean latency ms | Mean cycles | Model KiB | Operators KiB | Core KiB | Total flash KiB | Inference RAM KiB |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| DS-CNN | TFLM | 6.038 | 2,415,103 | 52.67 | 30.58 | **10.30** | 93.55 | 27.48 |
| DS-CNN | ExecuTorch | **5.825** | **2,330,141** | **37.67** | **23.92** | 12.11 | **73.70** | **26.00** |
| ResNet8 | TFLM | 15.653 | 6,261,149 | 96.19 | 25.46 | **10.29** | 131.94 | **54.51** |
| ResNet8 | ExecuTorch | **15.290** | **6,115,834** | **89.77** | **17.71** | 12.11 | **119.59** | 55.14 |
| MobileNetV1 0.25 | TFLM | 23.994 | 9,597,727 | 325.48 | 30.58 | **10.30** | 366.36 | 99.18 |
| MobileNetV1 0.25 | ExecuTorch | **21.450** | **8,579,895** | **253.07** | **23.92** | 12.11 | **289.10** | **85.15** |
| Deep autoencoder | TFLM | **1.205** | **481,860** | **270.48** | 7.79 | **9.52** | 287.79 | 9.64 |
| Deep autoencoder | ExecuTorch | 1.208 | 483,184 | 272.03 | **2.86** | 12.11 | **286.99** | **5.20** |

Each row averages **300 measured inferences across three boots**. The first call is
timed separately, followed by ten warm-ups and 100 measured calls per boot. Input
preparation, UART reporting and ET output checks are outside timing; caches are not flushed.
All 24 selected boots passed identity, timing and memory checks, and all 12 ET saved-output
checks passed. The final complete ET pass and prior final TFLM pass are used;
earlier captures remain preserved.

ET latency is 3.52% lower for DS-CNN, 2.32% lower for ResNet8 and 10.60% lower for
MobileNetV1. Autoencoder latency is close: ET is 0.27% higher, about 3.31 microseconds.
Integer pooling reduces ET RAM by 928–9,216 bytes versus v6. ET now uses less RAM
for DS-CNN, MobileNetV1 and the autoencoder; ResNet8 remains 648 bytes higher than
TFLM. ET filtered model + operators + core flash is lower on all four models.

**Flash scope:** Model is the serialized graph, weights and constants. Operators include
framework kernels/utilities, CMSIS-NN and selected resolver/registry code. Core covers
execution, allocation and planning. The total excludes runner, diagnostics, validation
fixtures, platform, MLEK adapters, shared toolchain/string pools and linker tables/padding;
it is not complete deployable MRAM size. Attribution of merged strings and COMDATs has
the limitations recorded in the detailed flash reports.

**RAM scope:** Accounted inference arena/pools, persistent runtime/kernel allocations,
outside persistent state, and ET runtime static storage. Excludes unused reservations,
stack high water, initialization workspace, transient heap peaks and benchmark/platform/
reporting memory. Persistent TFLM allocations are already inside the arena and are not
counted twice. These component costs are not whole-device deployment requirements.

**Model scope:** Both derive from trained reference weights; ET v8 retains DS-CNN's
Q/DQ cleanup and adds integer/list constant pooling. Quantization/calibration and
potentially preprocessing contracts differ. These are runtime/model measurements, not a dataset accuracy evaluation
or an official MLPerf result. Independent hardware timer cross-checking remains pending.

[Shareable SRAM HTML](results/e8-tiny-board-2026-09-17-sram-v8-v3.html) ·
[Exact CSV](results/e8-tiny-board-2026-09-17-sram-v8-v3.csv) · [JSON and collection provenance](results/e8-tiny-board-2026-09-17-sram-v8-v3.json) ·
[Both logging profiles](e8_tiny_profile_comparison.md) ·
[Integer-pooling RAM, latency and first-call deltas](e8_et_tiny_v8_results.md) ·
[Previous SRAM results](e8_tiny_board_results_2026_09_17.md) ·
[Previous ET v4 results](e8_et_tiny_v4_results.md)
