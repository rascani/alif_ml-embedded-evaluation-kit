<!--
SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates <open-source-office@arm.com>
SPDX-License-Identifier: Apache-2.0
-->

# E8 ExecuTorch Tiny benchmark bundle

The latest artifacts are [v5 paired size/latency builds](e8_tiny_optimized_builds.md).
The instructions and measurements below describe the earlier v4 experiment.

These four CPU-only images target the E8 DevKit's M55-HP at 400 MHz, using GCC 15.2.1,
CMSIS-NN 8.0.0, INFO logging, and model-specific operator and primitive selection.
The latest v4 bundle exposes method-owned input tensors directly. Planned inputs allocate
no extra buffer; unplanned inputs are allocated and bound once during initialization.
Inference executes without staging copies or per-call `set_input()`. PTEs, runtime sources,
operator/primitive selection, logging, SRAM reservations and benchmark settings are unchanged.
DS-CNN retains its DQ-to-Q pairs; the cleaned export is a separate change.

The v4 E8 run is complete: all 1,200 samples and 36 exact output checks passed, with
stable RAM, zero additional input allocation, and zero inference heap growth. The completed
second pass supplies the primary results; valid captures from the interrupted first pass
are retained separately. See the [v4 board report](e8_et_tiny_v4_results.md) for the capture
audit and updated TFLM comparison, and the [v3 report](e8_tiny_comparison.md) for the baseline.
The strict inference heap scope and separate 200-byte diagnostic allocation remain intact.

The PTEs use untrained seed-23 weights and 32 synthetic calibration samples. They are
graph/runtime benchmarks, not MLPerf accuracy results or matched-weight equivalents of
the trained TFLM reference models. DS-CNN retains two internal DQ-to-Q pairs. All models
have signed int8 I/O; CNN inputs are NHWC and the autoencoder input is NC. Classifiers
include quantized softmax. The original PTEs are embedded unchanged.

## Run on the Mac

Copy `build-e8-et-tiny-artifacts-v4.tar.gz` into `/Users/rja/alif`, then run:

```bash
cd ~/alif
tar -xzf build-e8-et-tiny-artifacts-v4.tar.gz
cd build-e8-et-tiny-artifacts-v4
/usr/bin/python3 run.py verify
/usr/bin/python3 run.py run all
```

The script uses `/Users/rja/app-release-exec-macos` and
`/dev/cu.usbmodem0012192765291` by default. Close any other serial reader. Follow its
prompts: SW4 to **SE** for programming, then **U4** for UART capture; reset three times
for each model, waiting for completion before each reset. It preserves the SE Tools
DEVICE configuration and boots the unsigned HP image from MRAM at `0x80008000`.

It verifies bundle checksums, model ID/hash, 100 timing samples, summary statistics,
RAM accounting, and all three output checks for every boot. Results go into
`results.csv`, `results.json`, and timestamped raw logs under `logs/`. The JSON retains
every cycle sample. A failed output comparison or incomplete capture is rejected.
Capture needs the same `pyserial` installation used for the TFLM runs.

To run one model, substitute `kws`, `ic`, `vww`, or `ad` for `all`. To regenerate a
combined result file from the saved captures:

```bash
/usr/bin/python3 run.py summarize all
```

To send results back without resending the firmware:

```bash
tar -czf ../e8-et-tiny-results-v4.tar.gz manifest.json results.csv results.json logs
```

All flashing, capture, and result-processing code is included in the archive. `run.py
--help` also documents port, tools directory, log directory, boot count, and timeout
overrides. Model identity hashes distinguish these ET images from the TFLM images even
though both suites use the same short IDs.

## Validated E8 measurements (v4)

These are aggregate means over 300 measured calls per model. Flash excludes the runner,
diagnostics, platform and shared support according to the attribution definition below.
RAM uses the scoped inference definition in the next section.

| Model | Mean latency (ms) | Model + runtime flash (B) | Accounted inference RAM (B) |
| --- | ---: | ---: | ---: |
| DS-CNN / KWS | 6.339553 | 117,920 | 49,916 |
| ResNet8 / IC | 15.172445 | 159,736 | 59,744 |
| MobileNetV1 / VWW | 21.426762 | 338,712 | 96,412 |
| Autoencoder / AD | 1.208801 | 324,060 | 6,248 |

The [v4 comparison report](e8_et_tiny_v4_results.md) includes TFLM results, ET RAM subdivisions,
percentile timings, and source/measurement limitations. Exact aggregates and all samples
are saved in [JSON](results/e8-et-tiny-2026-09-16-v4.json); the compact
[CSV](results/e8-et-tiny-2026-09-16-v4.csv) includes flash and RAM subdivisions.

## v4 input-storage change

These are confirmed E8 accounted RAM results, compared with the v3 E8 baseline.
Every model's three boots match the earlier M55 simulator RAM prediction exactly.

| Model | v3 E8 RAM (B) | v4 E8 RAM (B) | Reduction (B) |
| --- | ---: | ---: | ---: |
| DS-CNN / KWS | 50,462 | 49,916 | 546 |
| ResNet8 / IC | 62,872 | 59,744 | 3,128 |
| MobileNetV1 / VWW | 124,116 | 96,412 | 27,704 |
| Autoencoder / AD | 6,944 | 6,248 | 696 |

Input storage can overlap later activations in the plan. Callers must refill inputs
before every invocation; the benchmark and validation paths already do so. The adapter
retains method-owned tensor handles and removes its redundant TensorImpl vector and
input-pointer array. Specialized scalar inputs are bound once to their exported values.

The adapter uses ET's deprecated `Method::get_input()` at initialization because
`MethodMeta` exposes no data-pointer API; this is isolated to one call site. No ET source
patch is required. Native regressions cover exact planned addresses, zero planned-input
allocation, unplanned allocation/alignment, mixed tensors/scalars, changed inputs and
model reconstruction. All four Cortex-M PTEs pass 111 calls and three output checks each.
The v4 host manifest requires `Inputs allocated: 0 bytes.`, rejecting older staging images.

The [v4 build JSON](results/e8-et-tiny-build-2026-09-16-v4.json) records checks, source
identities and hashes; its [CSV](results/e8-et-tiny-build-2026-09-16-v4.csv) records flash.

## Measurements

Latency uses the same `synthetic_v1` input pattern and timer boundary as the TFLM suite:
one separately timed first inference, ten additional warm-ups, and 100 measured calls.
Inputs are filled before timing and UART printing happens after all measurements.
The application reports 111 benchmark invocations; the three additional validation
invocations run afterward and compare against the supplied lowered Python int8 outputs.
No cache flush occurs between calls; steady-state results describe warm execution.

RAM accounting includes these disjoint terms:

- Method pool usage: planned activations/kernel scratch plus runtime metadata, tensor
  descriptions, input storage, and allocation alignment. The planned bytes are a subset
  of this pool and are not added twice.
- Temporary allocator high-water mark over the 111 benchmark calls. Initialization
  high-water marks are reported separately, and output validation does not affect this
  measurement. The method pool must remain at its post-initialization size.
- `sizeof(EtModel)` and the retained heap delta across model initialization, including
  allocator wrappers and the adapter's tensor/container objects.
- Linked runtime/registry writable data and BSS, measured from the ELF and added by the
  host script as `runtime_static_bytes`.

`ram_accounted_peak_bytes` is the sum above. It excludes benchmark/platform memory,
the call stack, and unused arena/heap reservations. It is not a whole-device RAM peak.
The host requires unchanged retained heap usage across the 111 inference calls, after
benchmark sample storage is allocated and before statistics or printing. This is logged
as `MEMORY et_invoke ... scope=inference_batch_v1`; the manifest requires that exact
scope. `MEMORY et_diagnostics` reports allocations made while printing the benchmark;
the host saves `diagnostic_heap_delta_bytes` separately and excludes it from runtime RAM.
With this GCC/newlib, the first floating-point summary allocates 200 bytes. A standalone
M55 reproduction and the actual runner reproduce this allocation. Inference heap growth
still fails validation; the parser does not subtract a fixed 200-byte allowance.

The heap snapshots check retained usage, not transient heap peaks. The selected Cortex-M
kernels use planned scratch and the ET temporary allocator. Native adapter regressions
pass with glibc's default allocator settings.

The allocator wrapper now reads the underlying allocator's actual cursor, including
alignment padding. This fixes the earlier hand-maintained counter; old smoke-test
method/temp numbers should not be treated as an equally precise RAM baseline.

Both pools remain in SRAM for comparison with TFLM: method pool reserves 262,144 B at
`0x02000000`; temporary pool reserves 65,536 B at `0x02040000`. Normal writable globals,
heap and stack are in DTCM. Code/model/constants execute/read from MRAM. A later TCM or
multi-segment experiment can use the measured sizes to choose safe reservations.

## Recorded static footprint (v4)

All values below are bytes. Full image includes validation fixtures and shared support.

| ID / model | PTE | Planned buffers | Filtered runtime | Model + runtime | Full MRAM image |
| --- | ---: | ---: | ---: | ---: | ---: |
| kws / DS-CNN | 42,800 | 40,000 | 75,120 | 117,920 | 349,380 |
| ic / ResNet8 | 95,896 | 49,728 | 63,840 | 159,736 | 396,876 |
| vww / MobileNetV1 0.25 | 267,848 | 73,728 | 70,864 | 338,712 | 649,804 |
| ad / deep autoencoder | 279,968 | 768 | 44,092 | 324,060 | 552,308 |

| Runtime component | KWS | IC | VWW | AD |
| --- | ---: | ---: | ---: | ---: |
| ExecuTorch core | 39,188 | 39,188 | 39,188 | 39,188 |
| Cortex-M kernels and kernel utilities | 9,740 | 5,592 | 6,092 | 584 |
| CMSIS-NN | 20,228 | 14,156 | 20,228 | 1,552 |
| Registry and generated dispatch bindings | 5,964 | 4,904 | 5,356 | 2,768 |
| Runtime writable static RAM | 348 | 288 | 288 | 192 |

The flash subtotal excludes runner/diagnostics, fixtures, platform/startup, dedicated
logging objects, the MLEK adapter, shared C/C++ libraries, shared merged strings, and
linker tables/padding. Inline checks within retained runtime code remain included.
This is component attribution, not the size of a standalone deployable firmware.
Some excluded support is needed for inference. Cortex-M runtime checks remain enabled.

GNU ld merges strings from multiple objects into a pool, then attributes the entire
pool to its first object. We therefore report all `.rodata.str*` input sections as
shared strings, avoiding an inflated registry charge. Shared string pools are 32,135,
30,099, 30,339, and 26,779 B for KWS/IC/VWW/AD. Validation fixtures occupy 1,506, 9,246,
82,950, and 3,840 B respectively; these also stay outside the ML subtotal. The TFLM
accounting uses the same string rule; its previously recorded ML subtotals are unchanged.

`flash.csv` and `manifest.json` retain the costs. Each model directory includes the ELF,
MRAM binary, map, symbols, sections, selected operators, registry-capacity/primitive
headers, and `memory-attribution.json` with every retained contribution. Repository
records are in `docs/results/e8-et-tiny-build-2026-09-16-v4.json` and the accompanying CSV.

## Source and reproduction

The frozen exporter ZIP has SHA256
`f2a81a48a8d38d67c741c7beb4a98bc4db877cbc8517c43582ec2914321e84af`.
Its patch reconstructs ET tree `0510beb4b48b8785477a3c11b23c5bc18bd7841a` from base
`9250dc3537862db4f66bac07a8974dad81cc0f20`. This suite uses the isolated checkout
`resources_downloaded/et_tiny/executorch`; neither `dependencies/executorch` nor the
exporter's working tree was changed for this task. Apply and stage `export/source.patch`
in that checkout to reproduce the verified tree, without creating a commit.

The archive's `export/` directory preserves the original graphs, parameters, patch,
export script, validation fixtures, checksums and source/FVP/re-export reports. The
exporter's 12 M55 FVP runs matched the saved outputs exactly; E8 validation is separate.
Local native tests now exercise the integration/allocator and 111-call benchmark with
portable int8 and uint8 clone models. The int8 runner also passes three output checks.
Dedicated tensor tests cover both adapter constructors and ordinary/quantized byte types.
The four Cortex-M PTEs are also exercised using the actual E8 runner, adapter, selected
runtime, and kernel archives relinked with a Corstone M55 startup/linker and DWT timer.
Each completes 111 benchmark calls with unchanged inference heap, reports 200 bytes of
diagnostic allocations, and passes three exact output checks. These simulator runs
validate integration and accounting; their timing and memory placement are not E8
measurements. Logs and a check summary are included under `validation/`. Source changes
and new files are packaged for reproduction.

With the isolated source, existing build environment and GCC installed, build a fresh
bundle from the repository root:

```bash
resources_downloaded/env/bin/python scripts/py/build_et_tiny.py \
  --gcc-bin /home/rja/executorch/examples/arm/arm-scratch/arm-gnu-toolchain-15.2.rel1-x86_64-arm-none-eabi/bin \
  --bundle-name build-e8-et-tiny-reproduced
```

The script refuses to overwrite an existing bundle. It builds only the inference-runner
target, selects `forward`, verifies the frozen exports/source, embeds the validation
fixtures, accounts flash/RAM reservations, and packages the host scripts with SHA256SUMS.
