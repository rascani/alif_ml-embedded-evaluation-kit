<!--
SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates <open-source-office@arm.com>
SPDX-License-Identifier: Apache-2.0
-->

# Complete E8 Tiny profile comparison — 17 September 2026

Current flash uses **TFLM v3 INT8 registrations** and **ExecuTorch v6 with trained PTEs**, GCC 15.2.1
`-Oz` runtime/wrappers, CMSIS-NN 8.0.0 `-O3`, and function/data sections. The
current E8 latency/RAM fields are pending for both logging profiles. The last measured
board results below belong to earlier logging-enabled `-O3` images. No logging-disabled
latency or RAM has been measured on E8. The cleaned ET DS-CNN export is integrated;
ET v6 and TFLM v3 are ready for the E8 rerun. KiB means 1,024 bytes.

## Current flash and measurement status

| Model | Framework | Logging | Model KiB | Operators KiB | Core KiB | Total KiB | E8 latency | E8 RAM |
| --- | --- | --- | ---: | ---: | ---: | ---: | --- | --- |
| DS-CNN | TFLM | On | 52.67 | 33.35 | 11.59 | 97.62 | Pending | Pending |
| DS-CNN | TFLM | Off | 52.67 | 30.58 | 10.30 | 93.55 | Pending | Pending |
| DS-CNN | ExecuTorch | On | 41.42 | 27.56 | 23.25 | 92.23 | Pending | Pending |
| DS-CNN | ExecuTorch | Off | 41.42 | 23.92 | 12.11 | 77.45 | Pending | Pending |
| ResNet8 | TFLM | On | 96.19 | 28.08 | 11.58 | 135.85 | Pending | Pending |
| ResNet8 | TFLM | Off | 96.19 | 25.46 | 10.29 | 131.94 | Pending | Pending |
| ResNet8 | ExecuTorch | On | 93.90 | 21.28 | 23.25 | 138.43 | Pending | Pending |
| ResNet8 | ExecuTorch | Off | 93.90 | 17.71 | 12.11 | 123.71 | Pending | Pending |
| MobileNetV1 0.25 | TFLM | On | 325.48 | 33.35 | 11.59 | 370.42 | Pending | Pending |
| MobileNetV1 0.25 | TFLM | Off | 325.48 | 30.58 | 10.30 | 366.36 | Pending | Pending |
| MobileNetV1 0.25 | ExecuTorch | On | 264.45 | 27.56 | 23.25 | 315.26 | Pending | Pending |
| MobileNetV1 0.25 | ExecuTorch | Off | 264.45 | 23.92 | 12.11 | 300.47 | Pending | Pending |
| Deep autoencoder | TFLM | On | 270.48 | 8.49 | 10.77 | 289.75 | Pending | Pending |
| Deep autoencoder | TFLM | Off | 270.48 | 7.79 | 9.52 | 287.79 | Pending | Pending |
| Deep autoencoder | ExecuTorch | On | 273.41 | 3.95 | 23.25 | 300.60 | Pending | Pending |
| Deep autoencoder | ExecuTorch | Off | 273.41 | 2.86 | 12.11 | 288.37 | Pending | Pending |

Operators include framework kernels/utilities, CMSIS-NN and resolver/registry.
Core runtime includes execution, allocation and planning. Total sums model + operators + core;
runner, diagnostics, platform, validation fixtures, adapters, shared toolchain/string pools,
linker tables and padding are excluded. This is not the complete deployable MRAM image.
Exact totals are computed before rounding; merged-string and COMDAT attribution limitations remain.

## Operator component detail for current images

| Model | Framework | Logging | Framework kernels/utilities KiB | CMSIS-NN KiB | Resolver/registry KiB |
| --- | --- | --- | ---: | ---: | ---: |
| DS-CNN | TFLM | On | 10.71 | 22.12 | 0.53 |
| DS-CNN | TFLM | Off | 8.00 | 22.12 | 0.46 |
| DS-CNN | ExecuTorch | On | 5.40 | 18.96 | 3.19 |
| DS-CNN | ExecuTorch | Off | 2.96 | 18.96 | 2.00 |
| ResNet8 | TFLM | On | 11.39 | 16.16 | 0.53 |
| ResNet8 | TFLM | Off | 8.84 | 16.16 | 0.46 |
| ResNet8 | ExecuTorch | On | 5.01 | 13.07 | 3.20 |
| ResNet8 | ExecuTorch | Off | 2.63 | 13.07 | 2.01 |
| MobileNetV1 0.25 | TFLM | On | 10.71 | 22.12 | 0.53 |
| MobileNetV1 0.25 | TFLM | Off | 8.00 | 22.12 | 0.46 |
| MobileNetV1 0.25 | ExecuTorch | On | 5.40 | 18.96 | 3.19 |
| MobileNetV1 0.25 | ExecuTorch | Off | 2.96 | 18.96 | 2.00 |
| Deep autoencoder | TFLM | On | 2.67 | 5.55 | 0.27 |
| Deep autoencoder | TFLM | Off | 2.01 | 5.55 | 0.23 |
| Deep autoencoder | ExecuTorch | On | 0.45 | 1.52 | 1.98 |
| Deep autoencoder | ExecuTorch | Off | 0.27 | 1.52 | 1.07 |

## Last measured E8 latency and RAM — historical reference

These measurements used the original generic TFLM bundle and ET v4, with logging on,
GCC `-O3` and CPU-only Cortex-M55-HP at 400 MHz. Each row averages 300 inferences
across three boots. They do not quantify the effect of the new build settings or INT8 selection.

| Model | Framework | Mean latency ms | Mean cycles | Accounted inference RAM KiB |
| --- | --- | ---: | ---: | ---: |
| DS-CNN | TFLM original | 6.037 | 2,414,760 | 27.48 |
| DS-CNN | ET v4 | 6.340 | 2,535,821 | 48.75 |
| ResNet8 | TFLM original | 15.720 | 6,288,159 | 54.51 |
| ResNet8 | ET v4 | 15.172 | 6,068,978 | 58.34 |
| MobileNetV1 0.25 | TFLM original | 23.902 | 9,560,690 | 99.18 |
| MobileNetV1 0.25 | ET v4 | 21.427 | 8,570,705 | 94.15 |
| Deep autoencoder | TFLM original | 1.203 | 481,121 | 9.64 |
| Deep autoencoder | ET v4 | 1.209 | 483,520 | 6.10 |

RAM includes accounted inference arena/pools, runtime/kernel persistent allocations,
outside persistent state and ET runtime static storage. It excludes unused reservations,
stack high water, initialization workspace and benchmark/platform/reporting memory.

The historical ET v4 rows used untrained seed-23 weights. Current ET v6 uses trained reference
weights and removes the DS-CNN Q/DQ pairs; TFLM v3 uses trained reference models. Quantization
and calibration differ between frameworks. The historical timings do not describe ET v6.

[Exact CSV](results/e8-tiny-profile-comparison-2026-09-17-v6.csv) and
[JSON](results/e8-tiny-profile-comparison-2026-09-17-v6.json) preserve current and historical
records with explicit scope, image identity and blank/null fields for unavailable measurements.
They include the older images' flash components alongside their actual measured latency/RAM.

[ET v6 build report and Mac workflow](e8_et_tiny_v6_builds.md) ·
[INT8 registration report](e8_tflm_int8_registration_results.md) ·
[Historical measured report](e8_tiny_current_summary.md)
