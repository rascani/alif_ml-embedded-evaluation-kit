<!--
SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates <open-source-office@arm.com>
SPDX-License-Identifier: Apache-2.0
-->

# E8 ExecuTorch v4: direct input storage results

The completed second pass validates all four models: three boots per model, 1,200
measured calls, and 36 exact saved-output checks. Every boot reports zero additional
input-buffer allocation and zero retained inference heap growth. RAM is identical
across each model's boots and matches the M55 simulator prediction exactly.

This measures the adapter change that exposes ET's planned input storage directly and
removes the redundant staging buffer and per-inference `set_input()` copy. PTE hashes,
runtime sources, selected operators/primitives, benchmark settings, and memory regions
match v3. DS-CNN still contains its two internal DQ-to-Q pairs.

## Capture audit

The returned `results.json` and `results.csv` identify the complete second `run all`
pass, beginning at 15:40:41 on September 16. Both match independent recomputation from
the raw logs exactly, after normalizing the Mac/Linux log paths. The returned manifest
matches the frozen v4 firmware manifest exactly.

The interrupted first pass contains six valid boots: three each for KWS and IC. These
600 samples and 18 output checks are preserved as supplemental results and excluded
from the primary aggregates, keeping three boots per model in the comparison. Its
VWW capture, `vww-20260916-153947-894197.log`, begins at `Final results:` and lacks the
model identity, clock, and initialization records. The strict parser rejects it with
`Expected one BENCHMARK model record, found 0`. Its raw bytes are preserved; none of
its samples enters an aggregate. The later VWW capture passes all checks.

The [result JSON](results/e8-et-tiny-2026-09-16-v4.json) records the selection rule,
every log's SHA256, primary and supplemental samples, and the rejected capture.

## Latency and RAM versus v3

These are actual E8 M55-HP measurements at 400 MHz, CPU-only, GCC 15.2.1 `-O3`,
CMSIS-NN 8.0.0, with INFO logging and operator/primitive selection enabled.
Code/models remain in MRAM, pools in SRAM, and globals/heap/stack in DTCM.

Each boot separately times the first inference, runs ten additional warm-ups, and
measures 100 calls. Means and nearest-rank p95 values combine all 300 measured calls
per model. Input filling and UART reporting remain outside timing; caches are not
flushed between calls.

| Model | v3 mean (ms) | v4 mean (ms) | Latency change | v4 p95 (ms) |
| --- | ---: | ---: | ---: | ---: |
| DS-CNN / KWS | 6.351930 | 6.339553 | -0.19% | 6.344575 |
| ResNet8 / IC | 15.240949 | 15.172445 | -0.45% | 15.193558 |
| MobileNetV1 / VWW | 21.492134 | 21.426762 | -0.30% | 21.448768 |
| Autoencoder / AD | 1.218062 | 1.208801 | -0.76% | 1.210215 |

Per-boot mean spread is below 0.015% for every model. The small latency reductions
measure the whole adapter update, including any resulting code/data placement effects;
they do not isolate the cost of `memcpy` alone. Independent hardware timer verification
remains pending.

| Model | v3 RAM (B) | v4 RAM (B) | Saved (B) | Reduction |
| --- | ---: | ---: | ---: | ---: |
| DS-CNN / KWS | 50,462 | 49,916 | 546 | 1.08% |
| ResNet8 / IC | 62,872 | 59,744 | 3,128 | 4.98% |
| MobileNetV1 / VWW | 124,116 | 96,412 | 27,704 | 22.32% |
| Autoencoder / AD | 6,944 | 6,248 | 696 | 10.02% |

The removed input-pool allocations are 494 / 3,076 / 27,652 / 644 bytes for
KWS / IC / VWW / AD, including the four-byte input-pointer allocation. Removing the
redundant owning objects also saves 52 bytes per model outside the pool:
`sizeof(EtModel)` falls from 164 to 152, and retained initialization heap from 696 to
656 bytes. These terms exactly reconcile each saving above. Planned buffers, runtime
metadata, and runtime static RAM are unchanged.

The following disjoint v4 terms sum to accounted inference RAM:

| Model | Planned (B) | Method metadata (B) | Temp invoke peak (B) | Outside persistent (B) | Runtime static (B) |
| --- | ---: | ---: | ---: | ---: | ---: |
| DS-CNN / KWS | 40,000 | 8,760 | 0 | 808 | 348 |
| ResNet8 / IC | 49,728 | 8,920 | 0 | 808 | 288 |
| MobileNetV1 / VWW | 73,728 | 21,588 | 0 | 808 | 288 |
| Autoencoder / AD | 768 | 4,480 | 0 | 808 | 192 |

Initialization temporary peaks are separately 212 / 200 / 212 / 166 bytes. Each
image still reserves 262,144 bytes for the method pool and 65,536 for the temporary
pool. Accounted inference RAM excludes unused reservations, call-stack high water,
benchmark/platform memory, and reporting allocations; it is not whole-device peak
RAM. Heap snapshots establish retained usage, not transient heap peaks. The separate
200-byte diagnostic allocation remains identical on every boot.

## Updated comparison with TFLM

The TFLM baseline is unchanged. ET uses untrained seed-23 weights and synthetic
calibration; TFLM uses trained reference models. These are current graph/runtime
measurements, not matched-weight comparisons or MLPerf accuracy results. ET output
checks confirm agreement with its lowered Python int8 reference on three saved inputs.

| Model | TFLM mean (ms) | ET v4 mean (ms) | Latency change | TFLM RAM (B) | ET v4 RAM (B) | RAM change |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| DS-CNN / KWS | 6.036899 | 6.339553 | +5.01% | 28,136 | 49,916 | +77.41% |
| ResNet8 / IC | 15.720398 | 15.172445 | -3.49% | 55,816 | 59,744 | +7.04% |
| MobileNetV1 / VWW | 23.901726 | 21.426762 | -10.35% | 101,560 | 96,412 | -5.07% |
| Autoencoder / AD | 1.202803 | 1.208801 | +0.50% | 9,876 | 6,248 | -36.74% |

MobileNetV1 now uses 5,148 fewer accounted RAM bytes than TFLM. KWS's DQ-to-Q pairs
still drive its larger planned buffer; this adapter change leaves that work intact.
The [v3 delta analysis](e8_tiny_comparison.md#explanation-of-the-differences) records
the other metadata, kernel-constant and flash causes; its staging-buffer costs are
historical and are removed in v4.

### Autoencoder latency inspection

The remaining ET autoencoder gap is 2,399.01 cycles (5.9975 microseconds), or 0.499%:
483,520.24 cycles versus TFLM's 481,121.23. The v4 adapter update reduced the earlier
1.269% gap. Both graphs have ten INT8 fully connected layers with matching shapes and
264,192 weight elements. TFLM's ten filters each have one quantization scale and zero
weight zero point, and all output tensors have rank two; its wrapper therefore selects
the same per-tensor `arm_fully_connected_s8` path used directly by ET.

The linked `arm_nn_vec_mat_mult_t_s8` function is byte-identical in both firmware images:
1,420 bytes, SHA256 `f03203f30deae541075280f77456f1939702604d700e3e96bff9dba47de13136`.
Its addresses differ: TFLM `0x80028820`, ET `0x8002cd9c`.

One concrete memory difference is the 6,688-byte precomputed kernel-sum array: TFLM
allocates it persistently in the SRAM arena, while ET reads it from serialized model
constants in MRAM. That saves ET RAM but may change access/cache costs. ET also unpacks
operator arguments and constructs CMSIS parameters during each call; both runtimes
perform dispatch and wrapper work, whose relative cost has not been timed. Kernel-sum
placement, wrapper/dispatch overhead, and code/data alignment are hypotheses for the
remaining gap, not measured attributions. Model weights and quantization parameters
also differ. The gap exceeds observed within-build boot-to-boot variation, but the
whole-model timings cannot establish its cause.

To isolate it, measure time inside each CMSIS call separately from total invocation
time, then compare the same ET model with kernel sums copied once into SRAM at startup.
That experiment has not been run; current firmware and benchmark records are unchanged.

## First inference and warm execution

The first invocation after initialization is timed separately on each boot. Its mean
below uses three samples per model/runtime; the warm mean uses 300 calls after ten
additional warm-ups per boot. The penalty is first-call mean minus warm mean. No new
firmware or initialization timing was added for this analysis.

| Model | TFLM extra (microseconds) | TFLM change | ET v4 extra (microseconds) | ET v4 change |
| --- | ---: | ---: | ---: | ---: |
| DS-CNN / KWS | 109.43 | +1.81% | 103.01 | +1.62% |
| ResNet8 / IC | 10.14 | +0.06% | 57.64 | +0.38% |
| MobileNetV1 / VWW | 61.43 | +0.26% | 53.34 | +0.25% |
| Autoencoder / AD | 5.42 | +0.45% | 8.04 | +0.67% |

The first call exceeds its boot's warm p95 in all three boots for every model/runtime
except TFLM ResNet8. TFLM ResNet8's individual penalties are +31.14, -1.87 and +1.16
microseconds, so its small average does not establish a consistent first-call penalty.
For the autoencoder, the first-call means are 1.208220 ms (TFLM) and 1.216845 ms (ET),
versus warm means of 1.202803 and 1.208801 ms. ET's cross-runtime gap grows from about
6.00 microseconds warm to 8.63 microseconds on the first call.

These results are consistent with instruction/data cache warming and other first-use
effects, but do not isolate cache misses. Initialization has already touched model and
runtime data, and input preparation runs before the first timed invocation. TFLM's
autoencoder initialization also reads weights to compute kernel sums. Neither runtime
flushes caches before the first measurement, and their initialization access patterns
differ. Only three first-call samples are available; the result is a startup-state
comparison, not a controlled cold-cache experiment or proof of the MRAM hypothesis.

The [first-inference CSV](results/e8-tiny-first-inference-2026-09-16-v4.csv) records mean
times/cycles, absolute and percentage penalties, first-call ranges, and per-boot penalty
ranges. All individual first-call values remain in the original result JSON files.

## Flash

Filtered model-plus-runtime flash is unchanged from v3. Each full MRAM image shrinks
by 640 bytes in the excluded adapter/support portion.

| Model | TFLM model + runtime (B) | ET v4 model + runtime (B) | ET v4 full MRAM (B) |
| --- | ---: | ---: | ---: |
| DS-CNN / KWS | 148,848 | 117,920 | 349,380 |
| ResNet8 / IC | 193,068 | 159,736 | 396,876 |
| MobileNetV1 / VWW | 428,200 | 338,712 | 649,804 |
| Autoencoder / AD | 308,416 | 324,060 | 552,308 |

The filtered subtotal includes models, runtime core, kernels, CMSIS-NN and registry.
It excludes runner, diagnostics, validation fixtures, platform/startup, adapter, shared
C/C++ support/merged strings, and linker padding. It is component attribution, not
standalone deployable size. See the [component breakdown](e8_et_tiny.md#recorded-static-footprint-v4).

The [shareable summary](e8_tiny_current_summary.md) splits this subtotal into model,
operators, and core runtime. Operators include selected implementations, CMSIS-NN and
resolver/registry bindings; core runtime excludes all three. The
[exact component CSV](results/e8-tiny-flash-components-2026-09-16-v4.csv) preserves the
underlying byte counts and reconciles these categories to each subtotal above.

The subsequent [core flash audit](e8_et_core_flash_audit.md) found that the GCC toolchain
overrides function sections off. Isolated ResNet8 builds reduce ET core from 38.27 to
31.42 KiB by enabling them, or 23.36 KiB with runtime-only `-Os`, with logging enabled.
The results above remain the measured v4 firmware; neither alternative has E8 timings.

## Saved records

- [v4 JSON: provenance, capture audit, aggregates and all valid samples](results/e8-et-tiny-2026-09-16-v4.json)
- [v4 CSV: per-model latency, flash and RAM](results/e8-et-tiny-2026-09-16-v4.csv)
- [v3 to v4 CSV: latency and exact byte deltas](results/e8-et-tiny-v3-v4-2026-09-16.csv)
- [TFLM versus ET v4 CSV](results/e8-tiny-comparison-2026-09-16-v4.csv)
- [Frozen v3 report](e8_tiny_comparison.md) and [TFLM result JSON](results/e8-tflm-tiny-2026-09-16.json)

Returned archive: `build-artifacts/e8-et-tiny-results-v4.tar.gz`, SHA256
`85fa269f578170383e65ab9b18973ba7d862c62445a4921627efd153e2ac2c73`.
Raw logs, recomputed primary/supplemental CSV/JSON, and `analyze_results.py` are under
`build-artifacts/e8-et-tiny-results-v4/`. The firmware bundle, manifest, and historical
build/package records remain frozen; this report records the subsequent E8 validation.
