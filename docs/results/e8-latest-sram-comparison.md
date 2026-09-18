<!--
SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates <open-source-office@arm.com>
SPDX-License-Identifier: Apache-2.0
-->

Latest SRAM comparison: **ExecuTorch v8 (integer pooling)** vs **TFLM v3 (INT8 selection)**.
Cortex-M55-HP at 400 MHz, CPU-only. GCC 15.2.1: runtime/operators `-Oz`, CMSIS-NN 8.0.0 kernels `-O3`.

| Model | Framework | Latency ms | Mean cycles | Model KiB | Operators KiB | Runtime KiB | Total flash KiB | RAM KiB |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| DS-CNN | TFLM | 6.038 | 2,415,103 | 52.67 | 30.58 | **10.30** | 93.55 | 27.48 |
| | ExecuTorch | **5.825** | **2,330,141** | **37.67** | **23.92** | 12.11 | **73.70** | **26.00** |
| ResNet8 | TFLM | 15.653 | 6,261,149 | 96.19 | 25.46 | **10.29** | 131.94 | **54.51** |
| | ExecuTorch | **15.290** | **6,115,834** | **89.77** | **17.71** | 12.11 | **119.59** | 55.14 |
| MobileNetV1 0.25 | TFLM | 23.994 | 9,597,727 | 325.48 | 30.58 | **10.30** | 366.36 | 99.18 |
| | ExecuTorch | **21.450** | **8,579,895** | **253.07** | **23.92** | 12.11 | **289.10** | **85.15** |
| Deep autoencoder | TFLM | **1.205** | **481,860** | **270.48** | 7.79 | **9.52** | 287.79 | 9.64 |
| | ExecuTorch | 1.208 | 483,184 | 272.03 | **2.86** | 12.11 | **286.99** | **5.20** |

Bold indicates the lower value. KiB = 1,024 bytes.

- Flash uses logging-disabled builds and includes model, operators and runtime core; runner, platform, diagnostics and other support overhead are excluded.
- Latency and accounted inference RAM use logging-enabled builds. Each latency averages 300 inferences across three boots, after warm-up.
- RAM includes used inference pools and persistent runtime/kernel state; unused reservations, initialization workspace, stack and transient heap peaks are excluded.
- Both frameworks use trained reference weights, with different quantization/calibration. These are not official MLPerf results.
- The shared cycle timer passed an independent DWT cross-check on the E8: three boots, 72 intervals, including rollovers and 12-second runs. This does not calibrate the common CPU clock. [Timer validation](../e8_timer_validation.md).
