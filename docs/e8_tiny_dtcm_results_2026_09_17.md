<!--
SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates <open-source-office@arm.com>
SPDX-License-Identifier: Apache-2.0
-->

# E8 HP: SRAM versus DTCM inference pools

Moving inference pools to DTCM reduces latency for both frameworks on all four
models. TFLM improves more and now has the lower mean latency in every pair.
The convolutional-model margins between frameworks are small; the much larger
SRAM-to-DTCM improvements are the main result of this experiment.

The comparison uses ET v7 / TFLM v4 DTCM against the measured ET v6 / TFLM v3
SRAM baseline. Models, reservations, GCC 15.2.1, runtime/wrapper `-Oz`, CMSIS-NN
8.0.0 `-O3`, function sections, operator selection and the CPU-only 400 MHz HP
configuration are unchanged. ET integer-constant deduplication is not included.
Code and weights remain in MRAM; globals, heap and stack remain in DTCM.

## Latency and cycles

Each row averages 300 measured inferences over three boots. Change is
`100 × (DTCM / SRAM − 1)`; negative means lower latency. Timing uses logging-enabled
images. Per boot: one separately timed first call, ten warmups, then 100 measured
calls. Input preparation, reporting and output validation are outside timing.

| Model | Framework | SRAM ms | DTCM ms | DTCM mean cycles | Latency change |
| --- | --- | --- | --- | --- | --- |
| DS-CNN | TFLM | 6.037759 | 5.289914 | 2,115,965.54 | -12.39% |
| DS-CNN | ExecuTorch | 5.823769 | 5.316906 | 2,126,762.28 | -8.70% |
| ResNet8 | TFLM | 15.652873 | 13.627177 | 5,450,870.94 | -12.94% |
| ResNet8 | ExecuTorch | 15.231396 | 13.659699 | 5,463,879.62 | -10.32% |
| MobileNetV1 0.25 | TFLM | 23.994317 | 19.437068 | 7,774,827.29 | -18.99% |
| MobileNetV1 0.25 | ExecuTorch | 21.748097 | 19.580109 | 7,832,043.80 | -9.97% |
| Deep autoencoder | TFLM | 1.204650 | 1.145601 | 458,240.41 | -4.90% |
| Deep autoencoder | ExecuTorch | 1.207489 | 1.184098 | 473,639.11 | -1.94% |

ET's DTCM latency exceeds TFLM by 0.51% for DS-CNN, 0.24% for ResNet8, 0.74% for
MobileNetV1 and 3.36% for the autoencoder. In the SRAM baseline, ET led on the
three convolutional models and the autoencoder was nearly tied. Placement has
therefore changed the comparison substantially without changing kernels or models.

## Memory and flash

Every reported RAM component matches the corresponding SRAM baseline exactly,
including initialization peaks, arena head/persistent allocations, ET method and
temporary usage, outside persistent allocations and attributed runtime static RAM.
ET's inference temporary peak remains zero; its initialization temporary peak is
166–212 bytes. ET reports a stable inference heap, and TFLM reports zero allocation
calls during invocation. Transient heap and stack high water are not measured.

| Model | TFLM inference RAM B | ET inference RAM B | Change from SRAM |
| --- | --- | --- | --- |
| DS-CNN | 28136 | 29580 | 0 B, both |
| ResNet8 | 55816 | 59744 | 0 B, both |
| MobileNetV1 0.25 | 101560 | 96412 | 0 B, both |
| Deep autoencoder | 9876 | 6248 | 0 B, both |

These are accounted inference costs, not total reserved DTCM. The arena is 256 KiB
for TFLM; ET reserves a 256 KiB method pool plus a 64 KiB temporary pool. Including
globals, the 64 KiB heap and 32 KiB stack, total DTCM reservations are about 360 KiB
for TFLM and 424 KiB for ET. Initialization workspace and unused reservations are
excluded from the accounted inference table above.

Filtered model, operator and core flash sizes are unchanged in both logging profiles.
The [current comparison](e8_tiny_current_summary.md) includes the silent-build flash
breakdown; the [full profile table](e8_tiny_profile_comparison.md) keeps logging on/off
separate. Silent-build latency and RAM remain unmeasured. Frozen bundles and their
checksums have not been altered by importing results.

## First calls and repeatability

| Model | Framework | First mean ms | Steady mean ms | First overhead | Boot-mean span |
| --- | --- | --- | --- | --- | --- |
| DS-CNN | TFLM | 5.361382 | 5.289914 | +1.351% | 0.0006% |
| DS-CNN | ExecuTorch | 5.424645 | 5.316906 | +2.026% | 0.0025% |
| ResNet8 | TFLM | 13.648490 | 13.627177 | +0.156% | 0.0760% |
| ResNet8 | ExecuTorch | 13.666457 | 13.659699 | +0.049% | 0.1797% |
| MobileNetV1 0.25 | TFLM | 19.467222 | 19.437068 | +0.155% | 0.0045% |
| MobileNetV1 0.25 | ExecuTorch | 19.625853 | 19.580109 | +0.234% | 0.0041% |
| Deep autoencoder | TFLM | 1.160152 | 1.145601 | +1.270% | 0.1457% |
| Deep autoencoder | ExecuTorch | 1.194112 | 1.184098 | +0.846% | 0.0197% |

DS-CNN still has the largest first-call penalty, about 71 microseconds for TFLM and
108 microseconds for ET. The other overheads are at most 1.27%. There is no explicit
cache flush, so these are first-use observations rather than isolated cold-cache costs.
The DTCM benefit persists after warmup; it is not just a faster first inference.

ResNet8 is the closest framework comparison. ET's three boot means span 0.180%
and TFLM's span 0.076%, against a 0.239% aggregate ET-over-TFLM gap. All three
TFLM boot means are below all three ET means, but this is a small margin and the
runs were separate collections rather than interleaved paired trials. The 300
samples within a collection should not be treated as 300 independent experiments.
The SRAM-to-DTCM gains of 10–13% for ResNet8 are much larger than this variation.

## Interpretation

The results support inference-buffer access as a meaningful performance cost even
after warmup. DTCM provides local access without the SRAM/cache path. The largest
gain is TFLM MobileNetV1, which has the largest arena working set in this suite.
Cache capacity/conflicts and memory-access patterns are plausible contributors;
these measurements do not provide cache-miss or stall counters.

TFLM's larger improvement may also reflect persistent kernel data moving with its
arena. For example, its DS-CNN arena includes per-channel multiplier/shift arrays,
whereas ET stores corresponding parameter tensor payloads with the model in MRAM.
This is a plausible contributor, not a measured attribution of the difference.

The autoencoder benefits least: 4.90% for TFLM and 1.94% for ET. Its planned activation
storage is only 768 bytes, while model blobs are roughly 270 KiB. This is consistent
with less sensitivity to inference-buffer placement. Because weights were not moved,
the experiment does not resolve the earlier MRAM-weight-access hypothesis. A separate
weight-placement or per-operator experiment would be needed to establish that cause.

This comparison is substantially more controlled than the earlier compiler/model
update: models and flags are identical, as are filtered flash sizes, globals/heap/
stack placement, startup zero-table size and MRAM read-only section base addresses.
Pool relocations and firmware identity strings necessarily differ; arbitrary linked
symbol addresses were not all held constant. DTCM is the clear next baseline for
these HP measurements. Cross-framework results still use different quantization/
calibration paths and are not an official MLPerf accuracy or performance submission.

## Collection validation and provenance

Both returned manifests are byte-identical to their frozen firmware bundle manifests.
Reparsing the selected UART logs reproduces every field and sample in the returned
JSON. Build IDs, model hashes, 400 MHz clock, 111 invocations, ordered samples,
recomputed summaries, complete termination and RAM identities all pass. All 12 ET
saved native INT8 output checks pass, one example per model per boot. ET pool
addresses in UART match the DTCM linker audit. TFLM identity is checked against its
frozen DTCM image; its audit-mode log does not print an arena address.

ET contains exactly four captures with three boots each. TFLM contains the final
complete four-model pass, an earlier valid KWS/IC/VWW pass (nine boots), and one empty
AD capture. The final pass identified by returned `results.json` is used. Earlier
captures are preserved and validated but are not pooled into the reported averages.
Their three model means are within 0.04% of the final pass.

| Framework | Returned archive | SHA256 |
| --- | --- | --- |
| TFLM | build-e8-tflm-tiny-artifacts-v4-dtcm-results-20260917-142503.tar.gz | `a3a8c3e603b9d3b4512002b52405b94553ca69377ca8d805b59894132af27bb4` |
| ExecuTorch | build-e8-et-tiny-artifacts-v7-dtcm-results-20260917-140517.tar.gz | `4216320dfe08f7a953e327a27a3e31ce72af36d5d867f97b9719dff1a42102a3` |

Original archives and extracted logs remain under `build-artifacts/`; the extraction
and reproduction directory is `build-artifacts/collected-2026-09-17-dtcm`. Its
`record_results.py` reparses the collection and generates exact data records.
The JSON includes the baseline hash, all selected/excluded log hashes, per-boot
means and first calls, memory components, build identities and firmware hashes.

[Aggregate CSV](results/e8-tiny-board-2026-09-17-dtcm-v7-v4.csv) ·
[JSON and provenance](results/e8-tiny-board-2026-09-17-dtcm-v7-v4.json) ·
[Shareable comparison](results/e8-tiny-board-2026-09-17-dtcm-v7-v4.html) ·
[DTCM build/layout audit](e8_tiny_dtcm.md) ·
[Prior SRAM results](e8_tiny_board_results_2026_09_17.md)
