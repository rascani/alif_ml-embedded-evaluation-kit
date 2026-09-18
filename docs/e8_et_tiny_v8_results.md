<!--
SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates <open-source-office@arm.com>
SPDX-License-Identifier: Apache-2.0
-->

# E8 integer-pooling results — SRAM, 17 September 2026

Integer pooling delivers all predicted RAM savings on the E8. Compared with ET v6,
the new v8 images save 928–9,216 bytes of accounted inference RAM and 1,408–11,648
bytes of model flash. Operator/runtime flash and planned tensor storage are unchanged.
MobileNetV1 latency improves 1.37%; ResNet8 increases 0.38%. DS-CNN and the autoencoder
change by less than 0.04%.

The [current comparison](e8_tiny_current_summary.md) uses these ET v8 results and the
existing measured TFLM v3 SRAM baseline. TFLM was not rebuilt or recollected for this
export change. Both use Cortex-M55-HP at 400 MHz, CPU-only, GCC 15.2.1, `-Oz`
runtime/wrappers, CMSIS-NN 8.0.0 at `-O3`, and model-specific operator selection.
Code/models remain in MRAM; inference pools remain in SRAM; globals/heap/stack use DTCM.

## Collection validation

All 12 selected ET boots pass: three per model, each with one separately timed first
call, ten warm-ups, 100 measured calls and one exact saved native-output check.
There are 1,200 new measured inferences and 12 successful output checks. This is a
functional check of the saved example, not a new dataset accuracy evaluation.

The returned manifest is byte-identical to the frozen bundle and firmware tar.
Reparsing the raw UART reproduces every supplied result field and cycle sample.
Build/model identities, 400 MHz clock, iteration counts, summary statistics, memory
accounting, SRAM pool addresses and complete termination all pass. All reported
memory fields match the prior Corstone validation across every selected boot.

The archive contains the final four captures, three earlier valid captures (nine
boots), and two incomplete/malformed captures that lack boot identity. The final
complete pass named in `results.json` is used. Earlier attempts remain preserved
and are not pooled into these measurements. No selected capture is rejected; the
partial captures do not establish an inference failure.

Returned archive:
`build-e8-et-tiny-artifacts-v8-sram-integer-pooling-results-20260917-154311.tar.gz`

SHA256: `49dfb86e2adb353cc8fb695d0c50f2dbfe92a7a1f62dc0d25886a5f122e5d9b7`

The original archive and extracted verification copy remain under `build-artifacts/`
in `collected-2026-09-17-integer-pooling/et`. The exact JSON records all selected and
excluded log identities, checksums, per-boot samples and the reused TFLM provenance.

## Changes from ET v6

Positive latency change means slower. Each mean uses 300 measured calls after warm-up.

| Model | Old latency ms | New latency ms | New mean cycles | Latency change | Old RAM bytes | New RAM bytes | RAM saved bytes | Model flash saved bytes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| DS-CNN | 5.823769 | 5.825351 | 2,330,141 | +0.027% | 29,580 | 26,628 | 2,952 | 3,840 |
| ResNet8 | 15.231396 | 15.289585 | 6,115,834 | +0.382% | 59,744 | 56,464 | 3,280 | 4,224 |
| MobileNetV1 0.25 | 21.748097 | 21.449737 | 8,579,895 | -1.372% | 96,412 | 87,196 | 9,216 | 11,648 |
| Deep autoencoder | 1.207489 | 1.207960 | 483,184 | +0.039% | 6,248 | 5,320 | 928 | 1,408 |

Accounted RAM falls 9.98%, 5.49%, 9.56% and 14.85%, respectively. These are reductions
in occupied method storage; the reserved SRAM pools remain 256 KiB for method/planned
storage and 64 KiB for temporary storage. The PTE reductions are 9.05%, 4.39%, 4.30%
and 0.50%. In both logging profiles, filtered model + operators + core flash falls
by exactly the PTE reduction because every operator/core byte count is unchanged.

### RAM reconciliation

Bytes; identical across three boots per model. The temporary inference peak is zero
for all four. There is no separate input allocation, and the inference heap has no
retained growth. The method metadata includes EValues, tensor descriptors, integer-list
objects, instruction/argument tables and alignment.

| Model | Planned tensors | Old method metadata | New method metadata | Outside persistent | Runtime static | New accounted RAM |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| DS-CNN | 20,464 | 8,008 | 5,056 | 808 | 300 | 26,628 |
| ResNet8 | 49,728 | 8,920 | 5,640 | 808 | 288 | 56,464 |
| MobileNetV1 0.25 | 73,728 | 21,588 | 12,372 | 808 | 288 | 87,196 |
| Deep autoencoder | 768 | 4,480 | 3,552 | 808 | 192 | 5,320 |

The full RAM reduction is method metadata, consistent with fewer EValue slots and
integer-list allocations after pooling. Planned tensors, outside persistent state,
runtime static storage and temporary inference peak are unchanged. The PTE audit
also confirms unchanged weights, operations and tensor placement.

Accounted RAM excludes unused reservations, stack high water, initialization workspace,
transient heap peaks and benchmark/platform/reporting memory. Stable before/after heap
values do not measure transient heap high water. These figures do not establish the
minimum pool reservations required for initialization or whole-device RAM requirements.

### Interpreting the latency changes

DS-CNN's increase is about 1.58 microseconds and the autoencoder's is 0.47 microseconds;
both are practically unchanged. ResNet8 increases about 58.19 microseconds and
MobileNetV1 decreases about 298.36 microseconds.

The ResNet8 and MobileNetV1 shifts exceed the spread of their three current boot means
(0.060% and 0.008%, respectively). They are consistent within this collection, but
the samples within each boot are not independent evidence of a general speedup.

This change does not remove operator calls or change planned tensor offsets. It
shrinks the PTE and method metadata. A smaller metadata footprint can change cache
behavior; changes to MRAM constants and method metadata placement can also alter
alignment and cache conflicts. These are plausible explanations for the mixed timing
changes. The measurements contain no cache-miss counters or per-operator breakdown,
so they cannot identify the cause. The result supports a clear memory reduction,
with a model-dependent timing effect.

## Comparison with TFLM v3

All values below use SRAM inference pools. Flash is from separate silent builds;
latency and RAM are from logged board builds. The flash total is model + operators +
runtime core, excluding runner, diagnostics, fixtures, platform, adapters, shared
toolchain/string pools and linker overhead. It is not the full deployable MRAM image.

| Model | ET latency versus TFLM | ET accounted RAM versus TFLM | ET filtered flash versus TFLM |
| --- | --- | --- | --- |
| DS-CNN | 3.52% lower | 1,508 bytes lower (5.36%) | 21.22% lower |
| ResNet8 | 2.32% lower | 648 bytes higher (1.16%) | 9.36% lower |
| MobileNetV1 0.25 | 10.60% lower | 14,364 bytes lower (14.14%) | 21.09% lower |
| Deep autoencoder | 0.27% higher | 4,556 bytes lower (46.13%) | 0.28% lower |

DS-CNN now uses less accounted RAM than TFLM. ResNet8 is the only remaining case
with higher ET RAM: its metadata is 340 bytes larger, plus 20 additional outside
persistent bytes and 288 runtime-static bytes, totaling 648 bytes. ET filtered flash
is now smaller for all four models, including the autoencoder, whose PTE itself is
still larger than TFLM's model.

The [persistent-allocation comparison](e8_tiny_persistent_allocations.md) now traces
every TFLM arena-tail allocation and compares it with ET's method reconstruction.
For ResNet8, ET's larger tensor/value representation offsets savings from keeping
prepared kernel constants in the PTE. Both persistent totals reconcile exactly with
these board measurements.

Both frameworks derive from trained reference weights, but their quantization and
calibration differ.

## First inference after initialization

No explicit cache flush occurs. These are first-call effects, not isolated cache
miss costs. The first-call numbers also exclude model loading and initialization.

| Model | First mean ms | Steady mean ms | First-call overhead |
| --- | ---: | ---: | ---: |
| DS-CNN | 5.919325 | 5.825351 | +1.613% |
| ResNet8 | 15.276737 | 15.289585 | -0.084% |
| MobileNetV1 0.25 | 21.472382 | 21.449737 | +0.106% |
| Deep autoencoder | 1.213952 | 1.207960 | +0.496% |

[Current shareable comparison](results/e8-tiny-board-2026-09-17-sram-v8-v3.html) ·
[Exact aggregate CSV](results/e8-tiny-board-2026-09-17-sram-v8-v3.csv) ·
[JSON and collection provenance](results/e8-tiny-board-2026-09-17-sram-v8-v3.json) ·
[Per-boot samples](results/e8-et-tiny-2026-09-17-v8-sram.json) ·
[Both logging profiles](e8_tiny_profile_comparison.md) ·
[Build report](e8_et_tiny_v8_integer_pooling.md) ·
[Previous SRAM results](e8_tiny_board_results_2026_09_17.md)
