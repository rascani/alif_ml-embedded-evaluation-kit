<!--
SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates <open-source-office@arm.com>
SPDX-License-Identifier: Apache-2.0
-->

# ExecuTorch vs TFLM — current E8 results

[Complete logging-on/off flash comparison and historical latency/RAM](e8_tiny_profile_comparison.md)
records the latest builds separately from the board measurements below.

[ExecuTorch v6](e8_et_tiny_v6_builds.md) now uses the trained PTE bundle and cleaned
DS-CNN graph. It is ready for a combined rerun with TFLM v3 after local validation;
the historical measurements below remain unchanged.

**16 September 2026 · ExecuTorch v4 · Alif E8 Cortex-M55-HP · CPU-only, 400 MHz**

The new [17 September size/latency profiles](e8_tiny_optimized_builds.md) use `-Oz`,
CMSIS-NN `-O3`, function sections, and separate silent size builds. Their new flash
breakdown is recorded there; E8 latency reruns are pending. The measured values
below continue to describe the earlier binaries.

The latest [TFLM v3 INT8 registration flash table](e8_tflm_int8_registration_results.md)
reduces TFLM operator sizes further. The combined E8 rerun is waiting for the cleaned
ET DS-CNN export; no new timings are assigned to that table.

GCC 15.2.1 `-O3`, CMSIS-NN 8.0.0, logging enabled, model-specific operator selection.
ExecuTorch primitive selection is enabled with zero primitive registrations.
Code/models use MRAM; inference pools use SRAM; globals/heap/stack use DTCM.

**Lower is better; bold marks the lower value for each model and metric.** KiB = 1,024 bytes.

| Model | Framework | Mean latency (ms) | Mean cycles | Model flash (KiB) | Operators flash (KiB) | Core runtime flash (KiB) | Accounted inference RAM (KiB) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| DS-CNN | TFLM | **6.037** | **2,414,760** | 52.67 | 75.08 | **17.61** | **27.48** |
| DS-CNN | ExecuTorch v4 | 6.340 | 2,535,821 | **41.80** | **35.09** | 38.27 | 48.75 |
| ResNet8 | TFLM | 15.720 | 6,288,159 | 96.19 | 74.81 | **17.55** | **54.51** |
| ResNet8 | ExecuTorch v4 | **15.172** | **6,068,978** | **93.65** | **24.07** | 38.27 | 58.34 |
| MobileNetV1 0.25 | TFLM | 23.902 | 9,560,690 | 325.48 | 75.08 | **17.61** | 99.18 |
| MobileNetV1 0.25 | ExecuTorch v4 | **21.427** | **8,570,705** | **261.57** | **30.93** | 38.27 | **94.15** |
| Deep autoencoder | TFLM | **1.203** | **481,121** | **270.48** | 14.44 | **16.26** | 9.64 |
| Deep autoencoder | ExecuTorch v4 | 1.209 | 483,520 | 273.41 | **4.79** | 38.27 | **6.10** |

Mean latency and cycles use **300 measured inferences per model/runtime across three boots**.
Cycles are averaged from the raw measurements and displayed to the nearest whole cycle.
Each boot runs a separately timed first call, ten warm-ups, and 100 measured calls.
Input preparation and UART reporting are outside timing; caches are not flushed.
All 36 ET saved-output checks passed. The complete second ET pass supplies these results;
the interrupted first pass is retained separately.

**Model status:** ET uses untrained seed-23 weights and synthetic calibration; TFLM uses
trained reference weights. These are preliminary graph/runtime comparisons, not
matched-weight comparisons or MLPerf accuracy results. DS-CNN still has two internal
DQ-to-Q pairs pending cleanup. ET's redundant input staging and copy have been removed.
Independent hardware timer verification remains pending.

**Flash categories:**

- **Model:** serialized graph, weights, quantization data and other embedded constants.
- **Operators:** selected operator implementations/utilities, required CMSIS-NN kernels,
  and selected resolver/registry/dispatch bindings. This depends on the operator set and
  retained numeric variants; multiple models can share the same linked operator code.
- **Core runtime:** interpreter/executor, allocator, memory-planning and schema support.
  This is largely shared overhead, but the retained subset can vary with linking.

These three columns sum to the previously reported model-plus-runtime flash subtotal
before rounding. Runtime here means the core only; the earlier combined runtime subtotal
also included operators. ET core is 38.27 KiB in all four images. TFLM core varies from
16.26 to 17.61 KiB. KWS and VWW have identical TFLM operator costs because they select
identical operator sets despite different model sizes.

**Build-size caveat:** the current GCC configuration disables function sections, retaining
otherwise-unused functions. An [isolated ET ResNet8 audit](e8_et_core_flash_audit.md) reduces
core flash from 38.27 to 31.42 KiB by enabling them, or 23.36 KiB with runtime-only `-Os`.
Logging remains enabled and kernels retain `-O3`. These alternatives have not been timed
on the E8; the table continues to describe the measured binaries. TFLM uses the same
function-section setting and needs a corresponding audit.

**Memory scope:** Flash excludes runner, diagnostics, validation fixtures, platform,
adapter, shared C/C++ support/merged strings, and linker padding. RAM includes the
inference arena/pools, persistent runtime/kernel allocations, and outside persistent
state; ET also includes attributed runtime static storage. It excludes unused
reservations, call-stack high water, benchmark/platform state, and reporting allocations.
Initialization workspace and transient heap peaks are not represented in this inference
RAM figure. These are component costs, not whole-device deployment requirements.

[Detailed report](e8_et_tiny_v4_results.md) ·
[Exact table and flash components CSV](results/e8-tiny-flash-components-2026-09-16-v4.csv) ·
[Original aggregate comparison CSV](results/e8-tiny-comparison-2026-09-16-v4.csv) ·
[Shareable HTML](results/e8-tiny-comparison-2026-09-16-v4.html)
