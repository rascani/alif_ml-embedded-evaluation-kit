<!--
SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates <open-source-office@arm.com>
SPDX-License-Identifier: Apache-2.0
-->

# Plan: MLPerf Tiny comparisons on the Alif E8 Cortex-M55

Updated 18 September 2026. The four-model SRAM comparison is collected, validated
against its capture protocol, and analyzed. ExecuTorch v8 with integer pooling and
TFLM v3 with INT8 registrations are the frozen comparison baseline. Further runtime
optimizations are deferred. Independent timer validation now passes on the physical E8:
three boots, 72 samples and 144 comparisons against DWT. The planned comparison and
validation work is complete. Its documentation, diagnostic source and evidence are
published on the fork's `feat/e8-cpu-inference-runner` branch.

This plan replaces the original bring-up checklist. Historical smoke models, intermediate
exports and optimization experiments remain documented in their reports; their numbers
are not the current comparison.

## Objective and current scope

Compare CPU-only inference latency, cycles, model flash, operator/runtime flash, and
accounted inference RAM for DS-CNN, ResNet8, MobileNetV1 0.25 and the deep autoencoder.
Use trained reference weights, documented export/quantization differences and reproducible
firmware/model identities. This is a comparison using MLPerf Tiny models, not an official
MLPerf submission or an on-board dataset accuracy evaluation.

| Setting | Frozen comparison |
| --- | --- |
| Board/core | Alif Ensemble E8 DevKit, M55-HP, reported 400 MHz |
| NPU | Disabled; no delegate calls |
| Compiler | Arm GNU Toolchain 15.2.Rel1 / GCC 15.2.1 |
| Optimization | Runtime/operator wrappers `-Oz`; CMSIS-NN `-O3`; no LTO |
| Linking | Function/data sections and garbage collection |
| CMSIS-NN | 8.0.0, same source revision for both frameworks |
| Operator selection | Model-specific; compatible TFLM INT8 registrations; ET primitive selection enabled, none selected |
| Code/models | Internal MRAM |
| Inference pools | SRAM; method/arena at `0x02000000`, ET temp at `0x02040000` |
| Pool reservations | 256 KiB method/arena; ET 64 KiB temporary pool |
| Other RAM | Ordinary globals, heap and stack in DTCM |
| Timing | First call separately, 10 warm-ups, 100 measured calls, three resets per model |
| Input | Deterministic synthetic timing input; preparation outside timing |
| Logging | Enabled for timing/RAM; separate silent builds for flash |
| Board workflow | SE Tools on the Mac; packaged flashing, capture and collection scripts |

Dependencies were updated at implementation start, then frozen for reproducibility.
Do not refresh them merely because a newer upstream revision becomes available.
Authoritative identities are in the artifact manifests and build reports, including
ET runtime Git tree `0510beb4b48b8785477a3c11b23c5bc18bd7841a`. That is a tree identity
including staged export/runtime patches, not a commit ID. The exporter source revision
is recorded separately.

## Completed work

- [x] Port the ExecuTorch inference runner and build both CPU-only E8 variants with GCC.
- [x] Establish board programming, reset, readable UART capture and artifact transfer.
- [x] Implement repeated timing with first-call, mean, median, minimum, maximum, p95 and
  raw samples; exclude input preparation, output checks and UART formatting from timing.
- [x] Fix the SysTick sampling rollover race and test serviced/pending rollover cases
  against simulated registers. Independently validate the shared timer against DWT on
  the physical E8, including pending rollover and intervals exceeding 2^32 cycles.
- [x] Integrate all four trained Tiny exports and preserve model/runtime provenance.
- [x] Remove DS-CNN's redundant Q/DQ pairs and ET's redundant input staging buffers.
- [x] Enable model-specific ET operators, registry capacity and primitive selection.
- [x] Enable model-specific TFLM resolvers and compatible upstream INT8 registrations.
- [x] Verify compiler flags and shared CMSIS-NN identity; build silent and logged profiles.
- [x] Collect and reparse ET v8 and TFLM v3 SRAM board runs: 24 selected boots and 2,400
  measured inferences total, with 12 ET saved-output checks. Retain earlier attempts separately.
- [x] Validate all four TFLM INT8 registration changes against generic callbacks on the
  M55 simulator; validate ET runner outputs against the supplied frozen references.
- [x] Attribute flash separately to model, operators/CMSIS-NN/registry, and runtime core.
  Record full-image sizes and exclusions for runner, platform, diagnostics and adapters.
- [x] Report arena/method/planned use, inference temporary peaks, outside persistent state,
  ET static storage and reservations without double-counting persistent TFLM allocations.
- [x] Integrate integer/list pooling and verify all predicted RAM savings on the E8.
- [x] Trace every TFLM persistent arena allocation and reconcile all four totals with
  board observations; compare against ET's target-ABI/source method reconstruction.
- [x] Record current tables, first-call effects, per-boot/raw evidence and source identities.
- [x] Push the runner/build work to `fork/feat/e8-cpu-inference-runner` and remove the
  DTCM inference-pool experiment from that branch. Ordinary platform DTCM usage remains.
- [x] Write the separate metadata-optimization handoff; do not apply its proposed changes
  to this comparison baseline.

## Current results and evidence

The [current summary](e8_tiny_current_summary.md) is the primary comparison. It links
exact CSV/JSON and a shareable HTML table. Flash comes from silent builds; latency and
RAM come from logged board builds. No silent-build latency or RAM measurements are claimed.

| Model | TFLM mean ms | ET mean ms | TFLM accounted RAM bytes | ET accounted RAM bytes |
| --- | ---: | ---: | ---: | ---: |
| DS-CNN | 6.038 | 5.825 | 28,136 | 26,628 |
| ResNet8 | 15.653 | 15.290 | 55,816 | 56,464 |
| MobileNetV1 0.25 | 23.994 | 21.450 | 101,560 | 87,196 |
| Deep autoencoder | 1.205 | 1.208 | 9,876 | 5,320 |

- [ET v8 integer-pooling build guide](e8_et_tiny_v8_integer_pooling.md) and
  [measured results](e8_et_tiny_v8_results.md).
- [TFLM INT8 registration results](e8_tflm_int8_registration_results.md).
- [Both logging profiles](e8_tiny_profile_comparison.md).
- [Persistent-allocation comparison](e8_tiny_persistent_allocations.md), including the
  complete 340-byte ResNet8 method/tail difference.
- [Latest copyable Markdown table](results/e8-latest-sram-comparison.md).
- [Original board workflow](e8_board_smoke_test.md) and
  [benchmark/timer implementation history](e8_cpu_benchmark.md).

RAM is accounted inference storage, not whole-device peak RAM. Stack high water,
transient heap peaks, unused reservations and initialization workspace are excluded.
Framework quantization/calibration and potentially preprocessing contracts differ.
Producer-supplied quality validation and saved-output checks do not establish identical
end-to-end accuracy or a shared dataset evaluation on the physical board.

## Completed: independent timer validation

The [standalone timer diagnostic](e8_timer_validation.md) compares both
`Get_SysTick_Cycle_Count()` and the real HAL `CPU TOTAL` path against DWT CYCCNT.
It uses the same platform timer as both frameworks and does not alter their firmware.

- [x] Build the independent E8 image and package the Mac tools. All 39 Python tests pass;
  the extracted package verifies, reparses three synthetic boots, rejects an incomplete
  capture and collects the expected raw/CSV/JSON evidence. These are host checks, not a
  physical-board validation result.
- [x] Run three diagnostic boots on the Mac-connected E8 and return raw capture/results.
- [x] Reparse returned logs and check short intervals, many SysTick periods, a deliberately
  pending single rollover, forced DWT rollover, and a 12-second interval exceeding 2^32 cycles.
- [x] Record measured counter differences and read-bracketing uncertainty. All 72 samples
  pass on the physical board; both production counters fall inside the DWT bounds without
  the extra 32-cycle allowance. All three long cases service exactly 12,000 SysTick interrupts.

DWT and SysTick share the CPU clock. Agreement independently validates cycle accounting,
not the absolute accuracy of the 400 MHz frequency. The endpoint brackets are 240 cycles
wide in 69 samples and 391 cycles in the first zero-wait case of each boot. No timer
correction or rebuilding/rebenchmarking of the model images is indicated by this result.

The user ran `build-e8-timer-validation-artifacts-v1.tar.gz` on the Mac-connected E8.
The returned manifest and JSON/CSV results match the frozen bundle and reparsed UART.
The [dated JSON audit](results/e8-timer-validation-2026-09-18.json) records all samples
and archive/source identities. The [timer report](e8_timer_validation.md) retains the
run instructions and separate FVP limitation. No simulator pass is claimed; the physical
E8 evidence closes this item.

## Completed wrap-up

- [x] Publish the new analysis documents, refreshed plan, copyable table, handoff prompt
  and timer-validation source/evidence to
  [the fork branch](https://github.com/rascani/alif_ml-embedded-evaluation-kit/tree/feat/e8-cpu-inference-runner)
  after relevant checks.
- [x] Add the physical timer-validation outcome to the current summary and provenance.
  Preserve historical reports and firmware identities.

## Explicitly deferred or separate work

- Additional metadata optimizations, static descriptor changes and delegate-registry
  removal. Use the [handoff prompt](executorch_memory_savings_handoff.md) for a separate
  isolated investigation; none of its proposed savings has been applied here.
- Further dependency/compiler optimization experiments, including armclang.
- Model load/initialization benchmarking.
- A shared logical performance-input corpus and full dataset accuracy evaluation on
  the E8. Useful for a stricter end-to-end comparison, but not part of this wrap-up.
- Minimum deployment pool sizing, transient heap/stack high-water measurement, or a
  whole-device RAM claim.
- HE-core, NPU, power and official MLPerf submission work.

The DTCM inference-pool experiment was completed and removed from the supported fork
workflow at the user's request. Keep its locally preserved historical artifacts; the
active comparison remains SRAM. Do not turn remaining validation into another optimization
campaign.
