<!--
SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates <open-source-office@arm.com>
SPDX-License-Identifier: Apache-2.0
-->

# E8: disabling logging and selecting ExecuTorch primitives

This is a preserved footprint experiment. Active E8 and native builds now have
framework and HAL logging re-enabled, with ET primitive selection retained, so
benchmark results can be collected. See the [bring-up commands](e8_cpu_bringup.md#build-both-firmware-images)
and `build-artifacts/e8-cpu-logged-selective-bringup.tar.gz` for that configuration.

The restored logging-on images are **275,140 bytes (268.69 KiB) for ET** and
**344,308 bytes (336.24 KiB) for TFLM**. ET retains the three-slot, 36-byte registry;
selecting primitives saves 14,048 bytes (13.72 KiB) against the earlier logging-on
ET baseline. Both firmware builds and native test suites pass, and native runners
again emit initialization, profiling, and completion messages. E8 timing output
still needs board verification.

Measured on 2026-09-15. Disabling MLEK/framework and HAL logging saves **52,944 bytes
for ExecuTorch** and **15,600 bytes for TFLM**. Selecting ExecuTorch primitives from
the model saves a further **7,104 bytes** with logging disabled.

All images target E8 M55-HP, CPU-only, GCC 15.2.1 `-O3`, CMSIS-NN 8.0.0, with
ordinary operator selection enabled. Framework revisions, smoke models, and pool
placements match the [previous Bloaty baseline](e8_bloaty_comparison.md).
The models still differ; this is not a matched MLPerf Tiny footprint comparison.

## MRAM results

These are raw application image lengths, excluding ELF debug/container bytes.

| Configuration | ExecuTorch | TFLM |
| --- | ---: | ---: |
| Logging on; all ET primitives | 289,188 B (282.41 KiB) | 344,308 B (336.24 KiB) |
| Framework and HAL logging off; all ET primitives | 236,244 B (230.71 KiB) | 328,708 B (321.00 KiB) |
| Logging off; model-selected ET primitives | 229,140 B (223.77 KiB) | 328,708 B (321.00 KiB) |
| Final image excluding embedded model | 226,100 B (220.80 KiB) | 244,516 B (238.79 KiB) |

Logging saves 18.3% for ET and 4.5% for TFLM. Combined with primitive selection,
ET saves 60,048 bytes (58.64 KiB, 20.8%) against its logging-on baseline.
Excluding model bytes, the final ET image is 18,416 bytes (17.98 KiB) smaller than
TFLM for these different smoke workloads. Model objects remain 3,040 and 84,192 bytes.

For attribution, a separate intermediate build disabled only MLEK/framework logging
while retaining HAL logging: ET was 238,628 bytes and TFLM 331,060 bytes. The additional
HAL switch matters because application code also includes HAL's logging macros.

## Build controls

To reproduce this logging-off experiment, first configure the E8 build directories as
in [bring-up](e8_cpu_bringup.md), activate the Python environment, put the GNU Arm
toolchain on `PATH`, then run:

```bash
cmake -S . -B build-e8-et-cpu \
  -DMLEK_LOG_ENABLE=OFF -DHAL_LOG_ENABLE=OFF \
  -DMLEK_EXECUTORCH_SELECTIVE_BUILD=ON -DMLEK_EXECUTORCH_SELECT_PRIM_OPS=ON
cmake --build build-e8-et-cpu --target mlek_inference_runner -j12

cmake -S . -B build-e8-tflm-cpu \
  -DMLEK_LOG_ENABLE=OFF -DHAL_LOG_ENABLE=OFF -DMLEK_TFLM_SELECTIVE_BUILD=ON
cmake --build build-e8-tflm-cpu --target mlek_inference_runner -j12
```

`MLEK_LOG_ENABLE` now drives `EXECUTORCH_ENABLE_LOGGING` and TFLM's
`TF_LITE_STRIP_ERROR_STRINGS`. TFLM's flag propagates to consumers of its headers;
its debug-log callback is also omitted. These changes preserve optimization and
program-verification settings. The HAL logging header continues to expose its
standard I/O declarations with logging disabled, as existing Alif drivers require.

`HAL_LOG_ENABLE=OFF` disables HAL/application log macros. This removes normal
inference completion and `CPU TOTAL` reports as well as other diagnostics. The
logging-off images are useful for footprint analysis; retain the earlier logging-on
bundle for UART-driven bring-up, or add a dedicated results-output path before
using silent images for board timing measurements.

Direct platform/fault `printf` calls and toolchain termination diagnostics still exist.
These switches do not promise that every exceptional hardware path is silent.

## Primitive selection and RAM

The Cortex-M smoke model needs only its three `cortex_m::*` operators. The build
feeds the same model-derived `selected_operators.yaml` to ExecuTorch's upstream
primitive-header generator, enabling both `ET_PRIM_OPS_SELECTIVE_BUILD` and
`EXECUTORCH_ENABLE_PRIM_OPS_SELECTIVE_BUILD` on the existing runtime archive.
All 28 primitive kernels are omitted for this model; small registration scaffolding
remains. Other models retain any primitives present in their operator lists.

The upstream capacity generator always adds the full primitive allowance, so a local
generator sizes the fully selected registry from the YAML's kernel variants instead.
It rejects wildcard selections. An explicit `MAX_KERNEL_NUM` still overrides sizing.
With `MLEK_EXECUTORCH_SELECT_PRIM_OPS=OFF`, the upstream full-primitive sizing remains.

| DTCM item | ET baseline | ET final | TFLM baseline | TFLM final |
| --- | ---: | ---: | ---: | ---: |
| Initialized data | 5,468 B | 5,132 B | 5,060 B | 5,060 B |
| BSS | 3,912 B | 3,576 B | 3,384 B | 3,376 B |
| ET kernel registry, included in BSS | 372 B / 31 slots | 36 B / 3 slots | — | — |

ET removes 336 bytes of initialized primitive registrations and 336 bytes from its
registry, saving 672 bytes of DTCM reservations. TFLM removes eight bytes of BSS.
Both retain the 64 KiB heap and 32 KiB stack in DTCM. ET retains two 64 KiB SRAM pools
at `0x02000000` and `0x02010000`; TFLM retains its 64 KiB arena at `0x02000000`.
Arena high-water marks still require target measurement.

## Bloaty findings and validation

Logging removes diagnostic strings and their formatting/call-site code across both
runtimes. Primitive selection additionally removes `et_view`, `et_copy_index`, scalar
primitive lambdas, and otherwise-unused helpers such as `__ieee754_fmod`.

Both final images still contain 31,828 bytes of demangler/verbose-termination symbols.
`_vfprintf_r`, `_svfprintf_r`, `_vfiprintf_r`, and `_dtoa_r` also retain their baseline
sizes: together 24,812 bytes per image. Removing logging alone does not eliminate
these shared library paths; the earlier `std::terminate()` retention path remains.

Validation includes both E8 firmware links, both native CTest suites and silent native
runner executions, and registry-generator tests. A separate exported view/multiply
model requires `executorch_prim::et_view.default`; its selected build loads and passes
repeated-inference/reconstruction tests. Replacing it with the portable smoke model
restores the three-slot registry and passes again. E8 hardware execution is pending.

Reports and firmware snapshots are in `build-artifacts/logging-prim-comparison/`,
packaged as `build-artifacts/e8-logging-prim-comparison.tar.gz`:

- `et-logging-delta-*`, `tflm-logging-delta-*`: logging off minus logging on.
- `et-primitive-delta-*`: selected primitives minus all primitives, both logging off.
- `et-minus-tflm-final-*`: final framework comparison; positive means ET is larger.
- `summary.json`: exact payload sizes, model sizes, sections, registry symbols, hashes.
- `commands.sh`: commands for Bloaty 1.1, revision recorded in `manifest.json`.
- `et-nolog-prims/` and `tflm-nolog/`: final ELF, map, MRAM image, and CMake cache.

The reports use Bloaty's VM domain filtered to MRAM-stored sections, including
initialized DTCM data. Final section sums are 229,124 bytes for ET and 328,700 for
TFLM; adding 16 and eight bytes of alignment reconciles them to the raw images.
