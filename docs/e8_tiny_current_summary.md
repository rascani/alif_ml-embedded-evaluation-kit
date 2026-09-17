<!--
SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates <open-source-office@arm.com>
SPDX-License-Identifier: Apache-2.0
-->

# ExecuTorch vs TFLM — current E8 results

**17 September 2026 · ExecuTorch v7 · TFLM v4 · DTCM inference pools · Cortex-M55-HP · CPU-only, 400 MHz**

GCC 15.2.1 uses `-Oz` for runtime/operator wrappers and `-O3` for CMSIS-NN 8.0.0,
with function/data sections. Both frameworks select model-specific operators;
TFLM uses compatible INT8 registrations and ET has zero selected primitive registrations.
Code/models use MRAM; inference pools, globals, heap and stack use DTCM.
The models and compiler settings match the preceding SRAM experiment.

**Flash columns use the separate logging-disabled size builds. Latency, cycles and RAM
come from the logging-enabled board builds.** No latency or RAM is claimed for the silent
builds. KiB = 1,024 bytes; bold marks the lower value in each pair.

| Model | Framework | Mean latency ms | Mean cycles | Model KiB | Operators KiB | Core KiB | Total flash KiB | Inference RAM KiB |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| DS-CNN | TFLM | **5.290** | **2,115,966** | 52.67 | 30.58 | **10.30** | 93.55 | **27.48** |
| DS-CNN | ExecuTorch | 5.317 | 2,126,762 | **41.42** | **23.92** | 12.11 | **77.45** | 28.89 |
| ResNet8 | TFLM | **13.627** | **5,450,871** | 96.19 | 25.46 | **10.29** | 131.94 | **54.51** |
| ResNet8 | ExecuTorch | 13.660 | 5,463,880 | **93.90** | **17.71** | 12.11 | **123.71** | 58.34 |
| MobileNetV1 0.25 | TFLM | **19.437** | **7,774,827** | 325.48 | 30.58 | **10.30** | 366.36 | 99.18 |
| MobileNetV1 0.25 | ExecuTorch | 19.580 | 7,832,044 | **264.45** | **23.92** | 12.11 | **300.47** | **94.15** |
| Deep autoencoder | TFLM | **1.146** | **458,240** | **270.48** | 7.79 | **9.52** | **287.79** | 9.64 |
| Deep autoencoder | ExecuTorch | 1.184 | 473,639 | 273.41 | **2.86** | 12.11 | 288.37 | **6.10** |

Each row averages **300 measured inferences across three boots**. The first call is
timed separately, followed by ten warmups and 100 measured calls per boot. Input
preparation, UART reporting and ET output checks are outside timing; caches are not flushed.
All 24 selected boots and 12 ET saved-output checks pass. The final complete TFLM
pass is used; earlier captures remain preserved separately.

DTCM reduces TFLM latency by **12.39%, 12.94%, 18.99%, and 4.90%** for DS-CNN,
ResNet8, MobileNetV1 and autoencoder, respectively. ET reductions are **8.70%,
10.32%, 9.97%, and 1.94%**. Filtered flash and every accounted RAM component are unchanged.

TFLM now has the lower mean latency for every model. ET is 0.51%, 0.24%, 0.74%,
and 3.36% slower, respectively. ResNet8 is particularly close: boot-mean spans are
0.076% for TFLM and 0.180% for ET, so the small cross-framework margin should be
interpreted cautiously. The much larger placement gains are clear in both frameworks.
ET retains lower operator flash across all four and lower inference RAM for VWW/AD.

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

**Model scope:** Both derive from trained reference weights; ET v7 retains the cleaned
DS-CNN from v6. Quantization/calibration and potentially preprocessing
contracts differ. These are runtime/model measurements, not a dataset accuracy evaluation
or an official MLPerf result. Independent hardware timer cross-checking remains pending.

[Shareable HTML](results/e8-tiny-board-2026-09-17-dtcm-v7-v4.html) ·
[Exact CSV](results/e8-tiny-board-2026-09-17-dtcm-v7-v4.csv) · [JSON and collection provenance](results/e8-tiny-board-2026-09-17-dtcm-v7-v4.json) ·
[SRAM versus DTCM analysis](e8_tiny_dtcm_results_2026_09_17.md) ·
[Both logging profiles](e8_tiny_profile_comparison.md) ·
[Prior measured SRAM results](e8_tiny_board_results_2026_09_17.md)
