<!--
SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates <open-source-office@arm.com>
SPDX-License-Identifier: Apache-2.0
-->

# E8 board results — ET v6 and TFLM v3, 17 September 2026

This page records the measured ET v6 / TFLM v3 **SRAM baseline**, selected for the
[primary comparison](e8_tiny_current_summary.md). The subsequent
[DTCM experiment](e8_tiny_dtcm_results_2026_09_17.md) remains recorded separately. The
[profile table](e8_tiny_profile_comparison.md) keeps logging on/off separate.

## Collection validation

Both returned manifests are byte-identical to the manifests in their frozen firmware
packages. Every selected boot was reparsed with `scripts/py/tflm_tiny_results.py`; all
fields and individual samples reproduce the supplied results JSON exactly. Validation
checks build/model identity, 400 MHz clock, 111 invocations, ordered cycle samples,
recalculated summaries, complete termination and internally consistent memory totals.
There are 24 selected boots and 2,400 measured inferences. All 12 ET saved native-output
checks pass. This is one saved example per model on each boot, not a dataset accuracy test.

ET has exactly four captures, three boots each. TFLM has the final complete four-model
pass plus three earlier valid captures (nine boots) and one empty KWS capture. The final
pass named by the supplied `results.json` is used, without pooling the earlier attempts.
No selected capture was rejected. All original files remain in the returned archives.

| Framework | Returned archive | SHA256 |
| --- | --- | --- |
| ExecuTorch | build-e8-et-tiny-artifacts-v6-results-20260917-112519.tar.gz | `a463af66738cfd8ff5ed026b66d67caa8a6b1d57d3aa0e46aebcf4035a5728c3` |
| TFLM | build-e8-tflm-tiny-artifacts-v3-results-20260917-120927.tar.gz | `875756f7a8f44b83341c09887b2c9055afb97edc92d927f800c45334894869b8` |

The archives and extracted verification copies are retained under `build-artifacts/`
(verification directory: `collected-2026-09-17`). Exact per-boot records, all cycle
samples, selected/excluded log identities and checksums are recorded in the linked JSON.

## Accounted inference RAM

Bytes; values are identical across the three boots of each model/framework.

| Model | Framework | Planned/head | Persistent arena/method metadata | Outside persistent | ET runtime static | Total |
| --- | --- | --- | --- | --- | --- | --- |
| DS-CNN | TFLM | 20,464 | 6,884 | 788 | 0 | 28,136 |
| DS-CNN | ExecuTorch | 20,464 | 8,008 | 808 | 300 | 29,580 |
| ResNet8 | TFLM | 49,728 | 5,300 | 788 | 0 | 55,816 |
| ResNet8 | ExecuTorch | 49,728 | 8,920 | 808 | 288 | 59,744 |
| MobileNetV1 0.25 | TFLM | 73,728 | 27,044 | 788 | 0 | 101,560 |
| MobileNetV1 0.25 | ExecuTorch | 73,728 | 21,588 | 808 | 288 | 96,412 |
| Deep autoencoder | TFLM | 768 | 8,500 | 608 | 0 | 9,876 |
| Deep autoencoder | ExecuTorch | 768 | 4,480 | 808 | 192 | 6,248 |

TFLM's persistent tail includes runtime and kernel allocations; it is already part of
the arena. ET's temporary inference peak is zero in all four models, and its separate
input allocation is zero. ET inference heap is stable and TFLM reports zero allocation
calls during invocation. Equal before/after heap values do not measure transient heap
high water. No stack high water is measured.

The two frameworks now have identical planned/head sizes for all four models. The
remaining RAM differences are persistent metadata/kernel state and outside/static state.
For DS-CNN, ET uses 1,124 more metadata bytes, 20 more outside-persistent bytes and
300 runtime-static bytes: 1,444 bytes more overall. ET AD uses 4,020 fewer metadata bytes,
offset by 200 more outside-persistent and 192 static bytes: 3,628 bytes less overall.

The [DS-CNN metadata audit](e8_ds_cnn_metadata_audit.md) now reconciles ET's entire
8,008-byte method-metadata total. Its 214-entry EValue table uses 3,424 bytes;
repeated scalar/list constants are a candidate for export deduplication.

The reported inference costs exclude initialization workspace. TFLM initialization
arena peaks are near its 256 KiB reservation because of planner workspace behavior;
they are retained in the per-boot data and are not substituted for the inference costs.
ET reserves a 256 KiB method pool and 64 KiB temporary pool. These runs do not establish
the minimum arena reservations needed to initialize each model.

## First inference after initialization

The mean of the three separately timed first calls is compared with the mean of the
300 post-warm-up calls. No explicit cache flush occurs. This observes first-call effects;
it does not isolate cache misses from other first-use costs or interrupt variation.

| Model | Framework | First mean ms | Steady mean ms | First overhead |
| --- | --- | --- | --- | --- |
| DS-CNN | TFLM | 6.133665 | 6.037759 | +1.588% |
| DS-CNN | ExecuTorch | 5.928448 | 5.823769 | +1.797% |
| ResNet8 | TFLM | 15.652605 | 15.652873 | -0.002% |
| ResNet8 | ExecuTorch | 15.293453 | 15.231396 | +0.407% |
| MobileNetV1 0.25 | TFLM | 24.023981 | 23.994317 | +0.124% |
| MobileNetV1 0.25 | ExecuTorch | 21.813157 | 21.748097 | +0.299% |
| Deep autoencoder | TFLM | 1.209512 | 1.204650 | +0.404% |
| Deep autoencoder | ExecuTorch | 1.214443 | 1.207489 | +0.576% |

DS-CNN shows the largest first-call difference: about 96 microseconds for TFLM and
105 microseconds for ET. The other first-call means differ by less than 0.6%; TFLM
ResNet8's first mean is effectively equal to its warmed mean.

## Change from the previous measured images

Baseline: original generic TFLM and untrained ET v4, logging on and `-O3`. Current
images use `-Oz` runtime/wrappers, `-O3` CMSIS-NN and function sections; TFLM adds
INT8 registrations and ET has trained models plus DS-CNN cleanup. The changes were
applied together, so these deltas cannot be attributed to compiler optimization alone.

| Model | Framework | Latency change | RAM change bytes |
| --- | --- | --- | --- |
| DS-CNN | TFLM | +0.014% | +0 |
| DS-CNN | ExecuTorch | -8.136% | -20,336 |
| ResNet8 | TFLM | -0.430% | +0 |
| ResNet8 | ExecuTorch | +0.389% | +0 |
| MobileNetV1 0.25 | TFLM | +0.387% | +0 |
| MobileNetV1 0.25 | ExecuTorch | +1.500% | +0 |
| Deep autoencoder | TFLM | +0.154% | +0 |
| Deep autoencoder | ExecuTorch | -0.109% | +0 |

TFLM timing changes range from -0.43% to +0.39%, with unchanged inference RAM.
ET DS-CNN latency falls 8.14% and RAM falls 20,336 bytes (40.74%); the saved RAM
is exactly 19,536 planned-tensor bytes, 752 method-metadata bytes and 48 static bytes.
ET's other latency changes range from -0.11% to +1.50%, with unchanged accounted RAM.
The largest of those is VWW (+1.50%); this run does not isolate its cause.
All ET RAM totals match the earlier simulator accounting.

### Interpreting the optimization-related latency changes

The observed changes are mixed: only TFLM ResNet8 improves; ET DS-CNN and AD improve,
while ET ResNet8 and VWW regress. CMSIS-NN kernels remain at `-O3` in both frameworks.
Smaller `-Oz` runtime/wrapper code can improve instruction-cache locality and alter
MRAM fetch alignment; reduced inlining or other size-oriented choices can increase
executed instructions around kernel calls. These are plausible mechanisms, not measured
attributions. Function sections/linker layout, TFLM INT8 registrations and new ET
weights/quantization also changed. ET DS-CNN additionally removes four Q/DQ calls.

ET VWW's +1.50% change is consistent within the new collection: its three boot means
span only 0.0042%. It should not be dismissed as ordinary within-run noise, but these
runs cannot identify which configuration/model change caused it. An isolated compiler
comparison would use the same current PTE/TFLite, selection, sections, logging and
memory placement, varying only runtime/wrapper `-O3` versus `-Oz` while retaining
CMSIS-NN `-O3`. Per-operator versus executor timing could then help locate the cost.

[Exact aggregate CSV](results/e8-tiny-board-2026-09-17-v6-v3.csv) · [JSON, per-boot sources and archive audit](results/e8-tiny-board-2026-09-17-v6-v3.json)
