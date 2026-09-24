<!--
SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates <open-source-office@arm.com>
SPDX-License-Identifier: Apache-2.0
-->

# E8 Tiny: current SRAM results

**17 September 2026 · ExecuTorch v8 · TFLM v3 · Cortex-M55 HP · CPU-only, 400 MHz**

The final comparison uses trained reference models, GCC 15.2.1, CMSIS-NN 8.0.0,
`-Oz` runtime/operator wrappers, `-O3` CMSIS kernels, and selected operators.
Code/models use MRAM; inference pools use SRAM; globals/heap/stack use DTCM.

Start with the [build/run guide](e8_tiny_build_run.md). The
[measurement methodology](e8_tiny_methodology.md) defines the timing boundaries,
component attribution and exclusions. These are runtime/model measurements, not
an official MLPerf submission or shared dataset accuracy evaluation.

## Primary comparison

Flash uses logging-disabled size builds. Latency, cycles and RAM use logged board
builds. Each row pools 300 measured calls across three boots, after one separately
recorded first call and ten additional warmups per boot. KiB = 1,024 bytes.

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

All 24 selected boots passed identity, timing and memory checks, and all 12 ET
saved-output checks passed. The final complete ET pass and previously collected
TFLM v3 pass are used. Earlier attempts are preserved separately. The reported
flash total excludes runner/platform/shared support and is not deployable image
size. Inference RAM excludes unused reservations, stack high water, transient heap
peaks and initialization workspace.

## Logging-enabled flash

These are the companion images used for latency/RAM collection; all values are
bytes. Adding logging changes the image, so silent-build latency/RAM is unmeasured.
Model bytes are the same as the corresponding silent build.

| Model | Framework | Model | Operators | Core | Filtered flash |
| --- | --- | ---: | ---: | ---: | ---: |
| DS-CNN | TFLM | 53,936 | 34,154 | 11,870 | 99,960 |
| DS-CNN | ExecuTorch | 38,576 | 28,222 | 23,808 | 90,606 |
| ResNet8 | TFLM | 98,496 | 28,756 | 11,860 | 139,112 |
| ResNet8 | ExecuTorch | 91,928 | 21,794 | 23,808 | 137,530 |
| MobileNetV1 0.25 | TFLM | 333,288 | 34,154 | 11,870 | 379,312 |
| MobileNetV1 0.25 | ExecuTorch | 259,144 | 28,222 | 23,808 | 311,174 |
| Deep autoencoder | TFLM | 276,976 | 8,696 | 11,030 | 296,702 |
| Deep autoencoder | ExecuTorch | 278,560 | 4,040 | 23,808 | 306,408 |

## RAM components

Values are bytes. ET planned memory is already inside its method pool; TFLM
persistent memory is already inside its arena. The table separates those terms
without adding either twice. The metadata columns have different contents:
TFLM retains some kernel constants in RAM that ET stores in the model.

| Model | Framework | Planned/head | Metadata/persistent | Temp invoke peak | Outside persistent | Attributed runtime static | Total |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| DS-CNN | TFLM | 20,464 | 6,884 | 0 | 788 | 0 | 28,136 |
| DS-CNN | ExecuTorch | 20,464 | 5,056 | 0 | 808 | 300 | 26,628 |
| ResNet8 | TFLM | 49,728 | 5,300 | 0 | 788 | 0 | 55,816 |
| ResNet8 | ExecuTorch | 49,728 | 5,640 | 0 | 808 | 288 | 56,464 |
| MobileNetV1 0.25 | TFLM | 73,728 | 27,044 | 0 | 788 | 0 | 101,560 |
| MobileNetV1 0.25 | ExecuTorch | 73,728 | 12,372 | 0 | 808 | 288 | 87,196 |
| Deep autoencoder | TFLM | 768 | 8,500 | 0 | 608 | 0 | 9,876 |
| Deep autoencoder | ExecuTorch | 768 | 3,552 | 0 | 808 | 192 | 5,320 |

A zero in the static column means no additional cost is separately attributed in
this accounting; it is not a claim that the framework needs no other writable data.
ResNet8's ET total is 648 bytes higher: 340 bytes of method-versus-tail storage,
20 bytes of outside persistent storage and 288 bytes of attributed static storage.

## Integer-pooling savings

The ET v6 to v8 change shares integer/list constants. Weights, planned tensors,
operator calls, temporary inference peaks and outside/static storage are unchanged.
PTE reduction accounts for the filtered flash savings; all RAM savings are in
method metadata. These are used-byte savings; reserved pools were not resized.

| Model | PTE before → after | Flash saved | Method metadata before → after | RAM saved |
| --- | ---: | ---: | ---: | ---: |
| DS-CNN | 42,416 → 38,576 | 3,840 | 8,008 → 5,056 | 2,952 |
| ResNet8 | 96,152 → 91,928 | 4,224 | 8,920 → 5,640 | 3,280 |
| MobileNetV1 0.25 | 270,792 → 259,144 | 11,648 | 21,588 → 12,372 | 9,216 |
| Deep autoencoder | 279,968 → 278,560 | 1,408 | 4,480 → 3,552 | 928 |

## Evidence and archive

The [exact CSV](results/e8-tiny-board-2026-09-17-sram-v8-v3.csv) and
[JSON](results/e8-tiny-board-2026-09-17-sram-v8-v3.json) are retained byte-for-byte.
The JSON includes firmware/model identities, per-boot first-call and mean cycles,
RAM components, collection provenance, and the integer-pooling deltas. References
to older/per-boot reports inside it identify files preserved in the archive below.

The [physical timer cross-check](e8_timer_validation.md) passed on 18 September:
three boots, 72 intervals and 144 counter comparisons, including rollovers and
12-second runs. No timing correction or inference recollection was indicated.

Historical reports, detailed allocation/flash audits, per-boot samples and the
completed plan are preserved locally in:

`build-artifacts/e8-documentation-archive-2026-09-24.tar.gz`

SHA256: `14ea97a3d585dde37815d09e277f3096204a0cba9a9465cbf02d8bf08474400a`

Its internal `SHA256SUMS` verifies the original documents and data, stored under
`e8-documentation-archive/docs/`. It is a separate evidence artifact, not required
to build or package new firmware. Raw UART logs and original firmware bundles remain
in their existing `build-artifacts/` locations, identified by archived provenance.
The archive can be shared separately with a blog or investigation.
