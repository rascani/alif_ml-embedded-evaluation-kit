<!--
SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates <open-source-office@arm.com>
SPDX-License-Identifier: Apache-2.0
-->

# Plan: MLPerf Tiny model comparisons on the Alif E8 Cortex-M55

Compare TensorFlow Lite for Microcontrollers (TFLM) and ExecuTorch (ET) using MLPerf Tiny
models with CPU-only execution on one Cortex-M55 of the Alif E8 Ensemble DevKit.
Use the latest upstream frameworks with the same CMSIS-NN 8.0.0 and GCC toolchain for both.
Keep inference pools in SRAM. Implement a reproducible inference runner, establish model
correctness, and measure latency and memory use on the board.

Status: implementation started on `feat/e8-cpu-inference-runner`; both TFLM and ExecuTorch
board smoke inference and readable UART capture now pass. At 400 MHz, the first runs
reported 159,234 and 14,304 cycles respectively for different smoke models. ET reports
1,565 bytes peak method-pool usage and 166 bytes peak temporary-pool usage. A second ET
boot completed at 14,639 cycles with identical allocator usage and its own ET log path.
The E8 is connected to another host, so package firmware and metadata for transfer.
GCC is the agreed baseline; armclang is deferred. Both E8 firmware images now build,
and both native runner/test builds pass. See [the bring-up guide](e8_cpu_bringup.md)
for validated commands and transfer instructions. The initial images use different smoke models.
The benchmark loop is implemented and validated natively and on the E8. Both frameworks
completed three boots with 100 measured samples each. All 600 samples reproduce their
reported summaries. At 400 MHz, ET's mean times span 11.37–11.44 µs and TFLM's span
374.16–374.38 µs for different smoke networks. ET's allocator peaks are unchanged; TFLM
reports 4,160 bytes of arena usage on every boot. See [the board results](e8_cpu_benchmark.md).
Matched-weight Tiny models, dataset accuracy checks, and independent hardware timer checks
remain pending.
Updated ET Tiny model preparation is proceeding separately.

The initial optimized ET Tiny export is now integrated as a separate
[four-image SRAM bundle](e8_et_tiny.md), using the exporter's exact patched runtime,
GCC 15.2.1 and CMSIS-NN 8.0.0. Each image benchmarks 111 calls and then checks three
saved int8 input/output pairs. The first E8 attempt loaded DS-CNN but stopped before
inference: the adapter did not map ET `Char`/`Byte` to INT8/UINT8. The v2 bundle fixes
that mapping and completed DS-CNN inference on the E8: 100 measured calls averaged
6.35334055 ms and all three output checks passed. The host then rejected a 200-byte
heap increase from newlib formatting the floating-point summary. The v3 bundle measures
heap around inference before reporting, records diagnostic allocations separately, and
retains strict inference heap checks. All four actual runner/runtime integrations pass
111-call and three-output checks on a Corstone M55 simulator. The v3 E8 SRAM baseline
is now complete: all 1,200 measured samples and 36 exact output checks pass, RAM is
stable across the three boots per model, and inference heap growth is zero. Mean
latency is 6.351930 / 15.240949 / 21.492134 / 1.218062 ms for KWS / IC / VWW / AD;
accounted inference RAM is 50,462 / 62,872 / 124,116 / 6,944 bytes. See the
[comparison report](e8_tiny_comparison.md) and
[ET board results](results/e8-et-tiny-2026-09-16-v3.json). The exports have untrained
seed-23 weights and synthetic calibration, so they are not yet matched-weight/accuracy
comparisons with TFLM. DS-CNN still contains two DQ-to-Q pairs. A fix to the ET allocator
wrapper now measures actual alignment padding; earlier smoke RAM counters above retain
their historical values and should not be used as the corrected RAM baseline.
Static component sizes and provenance are recorded in
[JSON](results/e8-et-tiny-build-2026-09-16-v3.json) and
[CSV](results/e8-et-tiny-build-2026-09-16-v3.csv).

The four original INT8 TFLM Tiny reference models are now built for the SRAM baseline:
KWS, image classification, visual wake words, and anomaly detection. The
[TFLM Tiny package guide](e8_tflm_tiny.md) describes the included Mac flashing/capture scripts,
flash accounting, and arena/persistent RAM instrumentation. Native execution and allocator
tests pass for all four. The E8 SRAM baseline is complete: three boots per model, with all
1,200 measured samples and memory totals validated from the returned raw logs. Mean latency
is 6.037 ms (KWS), 15.720 ms (IC), 23.902 ms (VWW), and 1.203 ms (AD); peak inference
arena plus outside-persistent RAM is 28,136 / 55,816 / 101,560 / 9,876 bytes respectively.
See [the saved results](results/e8-tflm-tiny-2026-09-16.json). The models and source revision
are pinned in `scripts/py/tflm_tiny_models.json` for matching with the ET exports later.

The [flash attribution report](e8_tflm_tiny_flash.md) records full-image and filtered
model/runtime costs, with TFLM core, operator code, CMSIS-NN and resolver subdivisions.
Exact byte counts are saved in
[CSV](results/e8-tflm-tiny-runtime-detail-2026-09-16.csv) and
[JSON with object contributions and source mappings](results/e8-tflm-tiny-runtime-detail-2026-09-16.json).
Keep the documented exclusions and shared-library accounting consistent for the ET comparison.

The v4 ET bundle removes redundant staging input buffers and per-inference copies.
All four M55 simulator integrations and native planned/unplanned/mixed-input regressions
pass. The completed second E8 pass now validates all 1,200 timing samples and 36 output
checks. Accounted RAM is 49,916 / 59,744 / 96,412 / 6,248 B for KWS / IC / VWW / AD,
matching the predictions exactly; mean latency is 6.339553 / 15.172445 / 21.426762 /
1.208801 ms. Every boot reports zero additional input allocation and zero inference
heap growth. The interrupted first pass is audited separately; the v3 comparison is
preserved. See the [v4 board results](e8_et_tiny_v4_results.md) and
[input-storage notes](e8_et_tiny.md#v4-input-storage-change).

The immediate remaining work is:

1. Integrate each matched Tiny pair and validate known-input outputs.
2. Complete independent timer checks over long intervals; repeat the SRAM comparison
   when the matched ET exports and DS-CNN DQ-to-Q cleanup are ready.
3. Audit used and reserved SRAM pool sizes alongside persistent runtime allocations.

Research baseline: repository commit `91de84c8`, with ET runner changes examined from
[rascani/add-et-inference-runner](https://github.com/rascani/alif_ml-embedded-evaluation-kit/tree/e2a504e0d6a6b4a1d9812fe8cea205d639cae023).

**Experiment configuration**

CPU-only execution is the agreed scope. Use the M55-HP as the initial core, with the
following proposed baseline for both frameworks:

| Item | Configuration |
| --- | --- |
| Board | `TARGET_PLATFORM=alif`, `TARGET_BOARD=DevKit-e8` |
| CPU | `TARGET_SUBSYSTEM=RTSS-HP`, Cortex-M55, nominally 400 MHz |
| NPU | `ETHOS_U_NPU_ENABLED=OFF`; no Ethos-U delegated operators |
| Application | `USE_CASE_BUILD=inference_runner` |
| Linker layout | `LINKER_SCRIPT_NAME=RTSS-HP-infrun` |
| Frameworks | Latest upstream TFLM and ET, frozen to exact commits for each comparison |
| CMSIS-NN | Exactly `v8.0.0` for both frameworks and applicable export-side bindings |
| Compiler | Arm GNU Toolchain 15.2.Rel1 for both frameworks; armclang deferred |
| Optimization | Release, explicitly normalize relevant C/C++ and kernel builds to `-O3` |
| Memory | Internal MRAM for model/code; SRAM inference pools |
| Console | UART4, 115200 baud, 8N1 |
| Timing | `CPU_PROFILE_ENABLED=ON`, verified against the actual CPU clock |
| Peripherals | Disable display and camera use; keep the other application core inactive |
| Diagnostic tracing | ETDump/event tracing disabled; UART results enabled outside timed regions |

The initial objective is comparison using MLPerf Tiny models. Official MLPerf submission
integration, power measurement, NPU comparisons, and a second-core comparison are separate
follow-up work. Use SRAM inference pools for both frameworks and keep their placement
explicit in every result. Defer armclang to a later experiment. Treat the reported
armclang performance advantage as a hypothesis to measure on these models.

**1. Establish a pinned build environment**

- [x] Create implementation branch `feat/e8-cpu-inference-runner` from `main` (`91de84c8f0e6c24678e48d661f5861cdcb280b70`).
- [x] Initialize submodules, then update TFLM and ET to the latest upstream `main` revisions
  available when implementation starts. Record the resolved commits and freeze them for the
  experiment; refresh the whole comparison deliberately if dependencies change later.
- [ ] Upgrade framework wrappers, code generation, setup requirements, and any required Arm
  TFLM CMake integration together. Resolve compatibility problems against the latest sources
  rather than silently keeping this checkout's older framework revisions.
- [x] Locate Arm GNU Toolchain 15.2.Rel1. Use it for both firmware builds and record the version.
  Arm Compiler installation and licensing are deferred at the user's request.
- [ ] Choose Python/CMake/PyTorch versions supported by the updated frameworks and update the
  repository's pinned requirements accordingly. Reconcile the support package's current Python
  3.10–3.12 constraint if newer dependencies require a change.
- [x] Pin `dependencies/cmsis-nn` to `v8.0.0` and direct both framework builds to that same source
  checkout. Set TFLM's `CMSIS_NN_SRC_PATH` and ET's `CMSIS_NN_LOCAL_PATH` explicitly, adapting
  option names if the updated integrations change. Prevent a second implicit CMSIS-NN download.
- [ ] Match CMSIS-NN header options, rounding behavior, Helium/MVE selection, and scratch-size
  calculation bindings used during ET export. Validate the actual linked revision, not just a
  cache variable. CMSIS-NN version parity is required for the comparison.
- [ ] Set up the shared environment for both frameworks, restricting downloaded examples to
  `inference_runner` and skipping Vela model compilation:

  ```bash
  git submodule update --init --recursive -j8
  python3 set_up_default_resources.py \
    --ml-frameworks tflm executorch \
    --use-case inference_runner \
    --skip-vela
  source resources_downloaded/env/bin/activate
  ```

- [x] Verify that the Python ET exporter matches the updated ET source revision used for the
  C++ runtime. Re-export every `.pte` when that revision changes.
- [x] Capture compiler, CMake, Python package, framework, and submodule versions in the run manifest.

The following revisions were resolved at implementation start and are frozen for this
comparison. Refresh them together only when starting a new comparison baseline.

| Dependency | Observed source revision |
| --- | --- |
| TFLM `main` | `50b720726a25e39bc381187b0dd39669ac425262` |
| ET `main` | `80115201ee50342118b0a782ff7fa46a6fd67f97` (`version.txt`: `1.6.0`) |
| CMSIS-NN `v8.0.0` | `13c97dbb6f781d4aab38ed34e6e441f42b79aff4` (resolved commit) |

ET's observed [Cortex-M backend](https://github.com/pytorch/executorch/tree/80115201ee50342118b0a782ff7fa46a6fd67f97/backends/cortex_m)
defaults to CMSIS-NN `v8.0.0` and documents MLPerf Tiny validation. Its current export path
uses `CortexMQuantizer` and `CortexMPassManager`, which should replace assumptions based on
the old branch's export flow.

The historical ET runner branch pins ET `59b6220b` (`1.2.0a0`) while its requirements specify
`executorch==1.0.0`. Its setup script only checks whether ET is installed. Reuse its runner
changes with current setup/version checks rather than reproducing that mismatch.

Completion check: both environments use the selected latest framework commits, the same
CMSIS-NN 8.0.0, and verified exporter/runtime identity. The setup script's example model is
only a bring-up aid; it is not the Tiny suite.

**2. Port the ET runner and make the runtime build CPU-only**

- [x] Adapt the runner support from commit `53d7f8b9` to the current source paths and include names:
  - `source/app/use_case/inference_runner/usecase.cmake`
  - `source/app/use_case/inference_runner/src/MainLoop.cc`
  - `source/app/use_case/inference_runner/src/UseCaseHandler.cc`
- [x] Accept both framework names, require a model path for ET, and instantiate either
  `fwk::tflm::TestModel` or `fwk::et::EtModel` through the existing model interface.
- [x] Generate the embedded `.pte` and its required operator registrations using existing helpers.
  Keep model-independent inference handling shared between frameworks.
- [x] Add `MLEK_EXECUTORCH_SELECTIVE_BUILD=ON` for the inference runner. Select portable,
  quantized, and Cortex-M registrations from the PTE, and generate the runtime registry
  capacity from that list. `MLEK_EXECUTORCH_SELECT_PRIM_OPS=ON` also selects primitives;
  the smoke model needs none and uses a three-slot registry. Keep `-O3`.
- [x] Add `MLEK_TFLM_SELECTIVE_BUILD=ON` to generate the inference runner's TFLM resolver
  from the builtin operators used across all model subgraphs. Size it for distinct operators
  and validate its outputs against the generic resolver. Keep `-O3` and CMSIS-NN 8.0.0.
- [x] In `scripts/cmake/executorch.cmake`, make the Ethos-U backend depend on
  `ETHOS_U_NPU_ENABLED`. Keep the updated ET Cortex-M backend enabled for the embedded CPU build.
  In the research checkout, `EXECUTORCH_BUILD_ARM_BAREMETAL` enables the Ethos-U backend;
  it is not a general switch for all Cortex-M execution. Recheck upstream option semantics
  after the dependency update.
- [x] Change `generate_pte_ops_lib()` eligibility so CPU-only embedded builds still receive
  their portable operator registrations. Its current guard also depends on
  `EXECUTORCH_BUILD_ARM_BAREMETAL`, so switching off that flag alone is insufficient.
- [x] Check remaining backend/driver link dependencies and retain the native-host build path.
- [ ] Deferred: assess armclang feasibility after the GCC comparison. The local ET CMake file currently rejects
  `ARMClang`; investigate the updated runtime, generated operators, CMSIS-NN kernels, C++ library,
  and platform abstraction with a minimal CPU model before removing or narrowing that check.
- [ ] Deferred with armclang: audit GCC-specific flags and GNU linker assumptions, including whole-archive/registration
  handling, and implement the appropriate armclang/armlink equivalents where needed. Match
  Cortex-M55 architecture, hard-float ABI, enum size, and C++ runtime assumptions across objects.
- [x] Remove obsolete ET compatibility workarounds only after checking the updated dependency.
- [ ] Deferred: validate TFLM and ET with armclang, including operator retention and execution. If a concrete
  ET/compiler incompatibility remains, record it and use the same GCC toolchain for both as a
  labeled fallback while retaining armclang as the preferred outcome. Mixed-compiler numbers
  must not be presented as a framework-only comparison.
- [x] Verify both activation and temporary ET pools land in SRAM for the GCC control build:
  two 64 KiB pools at `0x02000000` and `0x02010000`, confirmed in the ELF/map. Recheck
  placement separately if the deferred armclang configuration is used.
- [x] Keep the existing TFLM runner behavior available, including its FVP loading option.
  Use embedded model data for this board experiment.

Keep `source/lib/` platform agnostic. Any later ET timestamp implementation that needs
Alif timing must live at the application/platform boundary. The old branch's ETDump changes
are optional follow-up work, with explicit cycle-to-time conversion if brought forward.

Completion check: build and run a small known model under each framework on M55-HP with
the NPU disabled, using the same GCC version for both. Confirm model outputs, CPU counters,
pool placement, and the absence of Ethos-U delegate calls and driver dependencies. Document
any compiler blocker before expanding to the full Tiny model set.

**3. Prepare equivalent MLPerf Tiny models and inputs**

- [ ] Pin an immutable revision of [MLCommons Tiny](https://github.com/mlcommons/tiny).
  Record the model files, trained weights, preprocessing, calibration data, and quality targets
  from that revision.
- [ ] Start with the standard workload families below. Confirm the selected revision's exact
  variants before exporting; include a larger image-classification variant only if selected.

  | Workload | Reference model family | Correctness metric |
  | --- | --- | --- |
  | Keyword spotting | DS-CNN | Classification accuracy |
  | Visual wake words | MobileNet | Classification accuracy |
  | Image classification | CIFAR-10 ResNet | Classification accuracy |
  | Anomaly detection | Dense autoencoder | Reconstruction scores and AUC |

- [ ] Bring up one compact model first, provisionally keyword spotting. Inspect its operators
  and ET Cortex-M support before committing to the export path for all models.
- [ ] Use the original reference `.tflite` for TFLM CPU execution, without Vela transformation.
- [ ] Locate or construct equivalent PyTorch model definitions and import the same trained
  weights. Account for padding, normalization, layout, and weight transformations explicitly.
  Inspect the updated ET backend's Tiny examples/tests for reusable definitions and weights
  before writing new conversions. Verify that they match the selected Tiny revision. There is
  no established `.tflite`-to-`.pte` conversion path in this repository.
- [ ] Validate the PyTorch floating-point implementation against the reference before quantizing.
- [ ] Export ET models through the updated Cortex-M path without an Ethos-U/TOSA delegate.
  At the observed upstream revision, the CLI target is `cortex-m55+int8`; verify the pinned
  revision's `CortexMQuantizer`/`CortexMPassManager` APIs and layout contract. Inspect the resulting
  operator list to identify CMSIS-NN kernels, portable fallbacks, and float operations.
- [ ] Match reference dtypes and quantization as closely as the backends allow. Match the
  input/output boundary so one framework does not silently include extra float conversions.
  Record unavoidable quantization differences and their accuracy effects.
- [ ] Generate a shared set of preprocessed examples and reference outputs. Preserve equivalent
  values through any layout changes; random byte input is unsuitable for correctness testing
  and can produce invalid floating-point values.
- [ ] Store export commands, model/input hashes, shapes, dtypes, quantization parameters,
  operator mappings, and numerical tolerances with each model's artifacts.

Completion check: each model pair passes numerical checks with documented tolerances and
meets the selected workload's quality target. Model conversion and CPU kernel coverage are
the main feasibility risks; do not substitute a different network without labeling it as a
different experiment.

**4. Add a repeatable CPU benchmark mode**

- [x] Add fixed synthetic input for initial benchmark workflow validation; refill every invocation.
- [ ] Replace synthetic input with the same logical samples for both frameworks. Embed a small
  performance corpus initially.
- [x] Add configurable warm-up and measured iteration counts. Start with 10 warm-ups and
  100 measured invocations, repeated across three independent resets for each model/framework.
  Refill input outside the timed region when necessary.
- [x] Time the model invocation, excluding input preparation, output checks, and UART printing.
  Disable noisy runtime diagnostics inside the measured invocation.
- [x] Record the first invocation separately from steady-state measurements. Treat initialization
  time as a separate metric if collected; do not mix it into inference latency.
- [ ] Verify the existing SysTick-derived `CPU TOTAL` counter, including elapsed intervals spanning
  SysTick interrupts. Record the actual core frequency and convert cycles to microseconds using it.
  The rollover race is fixed and simulated-register tests pass; board validation remains pending.
- [x] Collect per-invocation cycle counts and report count, mean, median, minimum, maximum, and p95.
  Print results after measurement in a machine-readable form and retain the raw serial log.
- [ ] Report reserved and observed memory separately: model bytes, firmware sections, tensor or
  method pool, ET temporary pool, and stack/heap usage where measurable.
- [ ] Audit flash comparisons: both runners now have model-specific operator selection.
  Use those options with equivalent Tiny model pairs and label generic-runner footprints
  separately. Retain the generated operator lists and capacity settings with each result.
- [ ] Provide an accuracy mode for known inputs and output extraction. Choose batching/transport
  after sizing the validation data; the whole accuracy dataset need not fit in the firmware.
- [ ] Keep the second core inactive and board settings constant. Verify code/model/buffer placement
  in linker maps and keep external RAM/flash out of the initial measurement path.

Completion check: repeated runs of the same binary produce valid outputs and stable statistics,
with enough recorded configuration to explain any variance.

**5. Publish reproducible build configurations**

Add two build configurations with the same CPU settings and distinct build directories. The
following is the intended armclang SRAM-control interface after dependency updates, compiler
enablement, and the ET CPU-only fixes are implemented; the paths are placeholders for model
artifacts. Use separate directories per framework, compiler, and model, with SRAM inference pools.

```bash
common=(
  -DTARGET_PLATFORM=alif
  -DTARGET_BOARD=DevKit-e8
  -DTARGET_SUBSYSTEM=RTSS-HP
  -DCMAKE_TOOLCHAIN_FILE=scripts/cmake/toolchains/bare-metal-armclang.cmake
  -DLINKER_SCRIPT_NAME=RTSS-HP-infrun
  -DUSE_CASE_BUILD=inference_runner
  -DETHOS_U_NPU_ENABLED=OFF
  -DCMAKE_BUILD_TYPE=Release
  '-DCMAKE_C_FLAGS_RELEASE=-O3 -g -DNDEBUG'
  '-DCMAKE_CXX_FLAGS_RELEASE=-O3 -g -DNDEBUG'
  -DGLCD_UI=OFF
  -DALIF_CAMERA_ENABLED=OFF
  -DCONSOLE_UART=4
  -DCPU_PROFILE_ENABLED=ON
  -DMLEK_LOG_LEVEL=MLEK_LOG_LEVEL_INFO
  "-DCMSIS_NN_SRC_PATH=$PWD/dependencies/cmsis-nn"
)

cmake -S . -B build-e8-tflm-armclang-sram "${common[@]}" \
  -DML_FRAMEWORK=TensorFlowLiteMicro \
  -Dinference_runner_MODEL_PATH=/absolute/path/model.tflite \
  -Dinference_runner_ACTIVATION_BUF_SZ=0x00200000

cmake -S . -B build-e8-et-armclang-sram "${common[@]}" \
  -DML_FRAMEWORK=ExecuTorch \
  "-DCMSIS_NN_LOCAL_PATH=$PWD/dependencies/cmsis-nn" \
  -Dinference_runner_MODEL_PATH=/absolute/path/model.pte \
  -Dinference_runner_ACTIVATION_BUF_SZ=0x00200000 \
  -DML_FWK_TMP_MEM_SIZE=0x00200000

cmake --build build-e8-tflm-armclang-sram --target mlek_inference_runner -j8
cmake --build build-e8-et-armclang-sram --target mlek_inference_runner -j8
```

- [ ] Verify effective compiler flags, including independently built TFLM/CMSIS-NN code, from
  build logs. Verify Helium/MVE kernels, floating-point behavior, and performance-affecting
  library options. Normalize flags for any GCC fallback too; its current default Release level
  is `-O2`, while TFLM uses `-O3` internally.
- [ ] Treat the 2 MiB pools above as starting reservations and size them per model after measuring.
- [ ] Document model selection, generated benchmark options, artifacts, and rebuild requirements.
- [ ] Document E8 programming using `bin/mlek_inference_runner.axf` or the generated MRAM binary.
  Check the programming configuration against HP's linker start address, `0x80008000`, and
  use a device configuration appropriate to the E8. Capture UART output from reset.

**6. Validate and record results**

- [ ] Add focused tests for framework selection, missing model paths, CPU-only operator
  registration, fixed-input inference, and correctness failures where those behaviors change.
- [ ] Adapt the TFLM-specific runner tests in `tests/use_case/inference_runner/` so enabling ET
  does not compile TFLM-only test code. Keep memory-failure checks appropriate to each allocator.
- [ ] Update `pytest/test_inference_runner.py`: it currently expects one inference and an
  `NPU ACTIVE` counter. The CPU benchmark must check the configured iteration count, CPU timing,
  successful completion, and correctness results. Make its reset method match the available hardware.
- [ ] Run relevant native tests and cross-build both E8 CPU variants with armclang. Test the
  required memory layouts and any retained GCC fallback. Check affected existing ET/NPU
  configurations for build regressions from dependency and backend gating changes.
- [ ] Run correctness checks on the physical E8, including the selected Tiny validation datasets,
  before accepting performance comparisons. Host/FVP results are functional checks, not board timing.
- [ ] Run the agreed repeated measurements, retaining binary/model hashes, manifests, linker maps,
  compiler commands, raw cycle counts, and serial logs.
- [ ] Produce a table per workload, compiler, and memory layout with accuracy/AUC, latency
  statistics, ET/TFLM latency ratio for matched conditions, model size, firmware footprint,
  per-bank memory use. Explain kernel fallbacks and any remaining differences in quantization,
  I/O conversion, or placement alongside the numbers. Include the planning policy and model hashes.
- [ ] Update the inference-runner documentation with CPU-only E8 instructions and the current
  `inference_runner_MODEL_PATH` option name.

Completion check: another developer can reproduce both builds and the reported CPU-only results
from the recorded revisions, model artifacts, commands, and board setup.

**Execution order and decisions**

Update frameworks and enforce CMSIS-NN 8.0.0 parity first. Resolve armclang feasibility and
the SRAM pool budget during runtime bring-up. Validate one model pair through export,
on-board correctness, and repeated SRAM timing next. Expand to the selected Tiny suite
after that path works.
Keep model-specific failures visible rather than hiding them behind suite averages.

Before model preparation, pin the Tiny revision and trained artifacts. Before hardware runs,
confirm the Arm Compiler installation, programming/reset interface, UART device, and usable
SRAM capacity. Start with M55-HP and the proposed measurement counts unless the first experiment
provides a reason to adjust them. A failure to build latest ET with armclang or CMSIS-NN 8.0.0
is an explicit implementation finding, not a reason to silently downgrade a dependency.

Research did not include a firmware build: submodules were uninitialized, and neither armclang
nor `arm-none-eabi-gcc` was available on `PATH`. The commands above are a target for implementation
and validation, not a claim that latest ET already builds with armclang in this checkout.

### 17 September 2026 — optimization profiles ready for board reruns

- Built ET v5 and TFLM v2: four models each, silent size and logged latency profiles.
- Enabled function sections; runtime/operator wrappers use GCC `-Oz`, CMSIS kernels `-O3`.
- Preserved CMSIS-NN 8.0.0, selected operators, empty selected ET primitive set, model bytes
  and memory placement. No ET source change was needed for this optimization step.
- All eight logged inference images passed simulator functional checks; their E8 MRAM
  binaries were reproduced exactly. All 16 images have compiler and flash attribution audits.
- [New flash report and packaged workflow](e8_tiny_optimized_builds.md) records the two
  profiles separately. Capture now checks firmware build identity; `run.py collect` packages returns.
- Next: rerun both four-model suites on the E8 and record new cycles, latency, and inference RAM.
  Existing board numbers remain tied to the previous `-O3` firmware.

### Follow-up: TFLM type-specific operator registration

The [int8 registration audit](e8_tflm_int8_registration_audit.md) confirms that our
TFLM v2 resolver still selects generic multi-type operator implementations. The
pinned CMSIS-NN backend provides int8 registrations for every numerical operator
in these four models; reshape should remain generic. Selecting these is the next
TFLM fairness improvement before the combined rerun with the cleaned ET DS-CNN.
The audit records retained s4/s16 code and remaining general initialization/int8
execution paths; existing artifact sizes have not been replaced with estimates.

### 17 September 2026 — TFLM INT8 selection completed

- Added type-aware registration generation across all nodes/subgraphs, selecting upstream
  CMSIS-NN INT8 APIs where compatible and keeping mixed signatures/reshape generic.
- Built TFLM v3 with four silent and four logged images; model bytes, core sizes,
  compiler settings, memory placement and ET artifacts are unchanged.
- Verified all selected registrations in linked symbols, all four full runners on
  Corstone-300, and 32 exact generic-versus-specialized output comparisons on Cortex-M55.
- Recorded [new flash tables and the packaged workflow](e8_tflm_int8_registration_results.md),
  including remaining shared preparation code and the INT16 pooling helper.
- Next: integrate the cleaned ET DS-CNN export, then rerun both suites on E8 for current
  cycles, latency and accounted inference RAM. Hardware runs remain deferred as requested.

### 17 September 2026 — cleaned trained PTE bundle integrated

- Imported all four trained PTEs from the supplied Q/DQ-cleanup ZIP, preserving the ZIP,
  source provenance, checksums and native input/output examples.
- ET v6 uses the existing runtime tree and both Oz/O3 profiles; DS-CNN now has 12
  operator calls, no internal Q/DQ, and 20,464 planned bytes instead of 40,000.
- The runner and capture parser carry the validation reference identity and sample count:
  the new bundle checks one supplied native example per model, outside timing.
- [ET v6 build report and Mac commands](e8_et_tiny_v6_builds.md) pair this bundle with
  unchanged TFLM v3. Historical v4/v5 and original TFLM results remain separate.
- Next: run ET v6 and TFLM v3 on E8, returning both timestamped result archives for the
  updated measured comparison. Do not reuse the untrained ET latency numbers for v6.
