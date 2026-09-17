<!--
SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates <open-source-office@arm.com>
SPDX-License-Identifier: Apache-2.0
-->

# TFLM INT8 registration results — 17 September 2026

The current ET partner is [v6 with trained weights and DS-CNN cleanup](e8_et_tiny_v6_builds.md).
TFLM v3 is unchanged; the ET v5 columns below preserve the pre-update comparison.

**TFLM v3** selects the upstream CMSIS-NN INT8 registrations for all numerical
operators in the four Tiny models. This reduces operator flash by **35–54%** versus
the generic registrations in v2. All eight E8 images build: four silent size
images and four logging-enabled latency images. The combined E8 collection with
ET v6 completed on 17 September; see the [current measured comparison](e8_tiny_current_summary.md)
and [collection validation](e8_tiny_board_results_2026_09_17.md).

## Operator flash before and after

Logging is disabled in this table; KiB = 1,024 bytes. Operators include the
framework kernels/utilities, CMSIS-NN and the selected resolver/registry.

| Model | TFLM generic v2 (KiB) | TFLM INT8 v3 (KiB) | Reduction | ET v5 reference (KiB) |
| --- | ---: | ---: | ---: | ---: |
| DS-CNN | 66.27 | 30.58 | 53.9% | 25.54 |
| ResNet8 | 55.82 | 25.46 | 54.4% | 17.71 |
| MobileNetV1 0.25 | 66.27 | 30.58 | 53.9% | 23.92 |
| Deep autoencoder | 11.93 | 7.79 | 34.7% | 2.86 |

The new TFLM operator totals break down as follows, in retained linker-map bytes:

| Model | TFLM kernels/utilities | CMSIS-NN | Resolver | Total operators |
| --- | ---: | ---: | ---: | ---: |
| DS-CNN | 8,190 | 22,648 | 476 | 31,314 |
| ResNet8 | 9,052 | 16,548 | 476 | 26,076 |
| MobileNetV1 0.25 | 8,190 | 22,648 | 476 | 31,314 |
| Deep autoencoder | 2,060 | 5,684 | 234 | 7,978 |

## Current flash comparison

All values below use silent images. TFLM model and core sizes are unchanged by
the registration change; ExecuTorch v5 is the existing reference bundle.

| Model | Framework | Model (KiB) | Operators (KiB) | Core runtime (KiB) | Total (KiB) |
| --- | --- | ---: | ---: | ---: | ---: |
| DS-CNN | TFLM v3 | 52.67 | 30.58 | 10.30 | 93.55 |
| DS-CNN | ExecuTorch v5 | 41.80 | 25.54 | 12.11 | 79.44 |
| ResNet8 | TFLM v3 | 96.19 | 25.46 | 10.29 | 131.94 |
| ResNet8 | ExecuTorch v5 | 93.65 | 17.71 | 12.11 | 123.46 |
| MobileNetV1 0.25 | TFLM v3 | 325.48 | 30.58 | 10.30 | 366.36 |
| MobileNetV1 0.25 | ExecuTorch v5 | 261.57 | 23.92 | 12.11 | 297.60 |
| Deep autoencoder | TFLM v3 | 270.48 | 7.79 | 9.52 | 287.79 |
| Deep autoencoder | ExecuTorch v5 | 273.41 | 2.86 | 12.11 | 288.37 |

[Exact CSV](results/e8-tflm-int8-registration-2026-09-17.csv) and
[JSON](results/e8-tflm-int8-registration-2026-09-17.json) record all 24 images:
TFLM v2, TFLM v3 and ET v5, each with both profiles. They include model, firmware
and ELF hashes, component byte counts, and complete MRAM payload sizes. The tables
exclude runner, platform, diagnostics, validation fixtures, MLEK adapters, shared
toolchain/string pools, linker tables and padding. These attributed totals are
not standalone deployable firmware sizes; some excluded support is necessary.
Merged-string and COMDAT ownership retain the earlier attribution limitations.

TFLM models use trained reference weights. The ET v5 models in the historical tables
above use untrained seed-23 weights and synthetic calibration, with DS-CNN DQ/Q pairs.
The current ET v6 comparison uses trained weights and removes those pairs.
The model-byte differences are therefore not matched-weight format comparisons.
Historical E8 latency/RAM values remain associated with their original binaries.

## Selection and remaining differences

The generator inspects every node in every subgraph. It selects an INT8
registration only if every use of that builtin has a compatible signature:
INT8 activations, outputs and weights, with INT32 or absent biases where allowed.
Mixed signatures and unavailable specializations retain the generic registration.
This avoids narrowing an INT4-weight or INT16 operator accidentally.

The available selections used here are `Register_CONV_2D_INT8`,
`Register_DEPTHWISE_CONV_2D_INT8`, `Register_FULLY_CONNECTED_INT8`,
`Register_AVERAGE_POOL_2D_INT8`, `Register_ADD_INT8` and `Register_SOFTMAX_INT8`.
Reshape stays generic. The generated calls are guarded by `CMSIS_NN`; other
backends retain their original registrations. Each image includes
`selected_tflm_operators.json` with the inspected signatures and selection reasons.
The symbol audit verifies each selected registration is linked and its generic
counterpart is absent.

One upstream limitation remains: **848 bytes of `arm_avgpool_s16`** are retained
in each CNN image because the INT8 pooling callback calls a shared quantized
helper that also dispatches INT16. Small s4/s16 buffer-size queries also survive
shared preparation code. Together, s4/s16-named CMSIS objects occupy 932 bytes
in DS-CNN/VWW, 888 bytes in ResNet8 and 4 bytes in the autoencoder. This change
uses the upstream registration APIs without modifying the TFLM kernels.

TFLM also retains general `Prepare` logic for quantization parameters, scratch
requirements and optional type-specific setup. Its INT8 fully connected path
supports per-channel quantization and a 1x1 convolution route, and computes kernel
sums during initialization. ET's linear wrapper calls `arm_fully_connected_s8`
directly and stores precomputed sums in the PTE. These help explain the remaining
operator gap; narrower registration does not make the two implementations identical.

## Build settings and validation

GNU Arm 15.2.1 compiles the runtime and wrappers at `-Oz`, CMSIS-NN 8.0.0 at `-O3`.
Function/data sections and linker garbage collection remain enabled, with no LTO.
Both profiles preserve `KERNELS_OPTIMIZED_FOR_SPEED` and compiler builtins as
required by the [CMSIS-NN guidance](../dependencies/cmsis-nn/README.md#compiler-options).
Code/models remain in MRAM, the 256 KiB arena in SRAM at `0x02000000`, and globals,
heap and stack in DTCM. ET primitive selection and ET artifacts are unchanged.

Completed checks:

- All eight E8 images pass compiler, selected-registration and flash attribution audits.
- All four logged E8 MRAM images reproduce byte for byte before simulator validation.
- Their linked inference libraries complete 111 invocations per model on Corstone-300.
- A separate Cortex-M55 probe compares generic versus INT8 CMSIS-NN registrations:
  **32 byte-exact output matches**, eight input patterns per model. It also checks
  that the actual invoke callbacks differ for every specialized operator.
- Four native model test/inference runs exercise the non-CMSIS fallback. The 30
  Python tests cover generation, mixed signatures, missing APIs and benchmark tooling.

The comparison probe uses zero, minimum, maximum, ramp and four deterministic
pseudorandom INT8 input patterns. Its generic and specialized versions link the
same CMSIS-NN library. The probe is a separate validation ELF and contributes no
bytes to the reported firmware. Simulator logs and `validation/fvp/checks.json`
are included. These checks establish functional equivalence on the test inputs;
they are not an MLPerf accuracy evaluation or new E8 timing/RAM measurements.
Silent images receive static checks; execution validation uses the logged profile.

## Packaged Mac workflow

The archive is `build-e8-tflm-tiny-artifacts-v3.tar.gz`, with a separate `.sha256`
file. It includes the binaries, models, linker maps, ELF symbols, compiler audits,
selection manifests, validation evidence and all capture/collection scripts.
The earlier bundles remain intact. The completed board collection used these commands;
they are retained here for reproduction:

```bash
cd ~/alif
shasum -a 256 -c build-e8-tflm-tiny-artifacts-v3.tar.gz.sha256
tar -xzf build-e8-tflm-tiny-artifacts-v3.tar.gz
cd build-e8-tflm-tiny-artifacts-v3
/usr/bin/python3 run.py verify
/usr/bin/python3 run.py run all
/usr/bin/python3 run.py collect
```

The script uses the established SE Tools and UART setup, prompts for the SE/U4
switch, and requests three resets per model. It flashes the **logging-enabled**
`<model>/mram.bin`; images in `size/<model>/` are silent and used only for size
accounting. Each boot records one first inference, ten additional warm-ups and
100 measured inferences. The parser checks the model hash and new firmware build
ID. `collect` creates a timestamped results tar in the parent directory to copy back.

## Reproduction

The inference-runner CMake option is `-DMLEK_TFLM_SELECT_INT8_OPS=ON`, used with
`-DMLEK_TFLM_SELECTIVE_BUILD=ON`. The general default is OFF; the Tiny TFLM builder
enables it. The generator CLI also accepts `--select-int8`.

From the repository root, set `GCC_BIN` and `FVP` to the toolchain directory and
Corstone-300 executable. Use a fresh bundle name for another build:

```bash
resources_downloaded/env/bin/python scripts/py/build_tflm_tiny.py \
  --gcc-bin "$GCC_BIN" --paired-profiles \
  --bundle-name build-e8-tflm-tiny-artifacts-v3 --no-package
resources_downloaded/env/bin/python scripts/py/validate_tiny_fvp.py \
  --bundle build-e8-tflm-tiny-artifacts-v3 --build build-e8-tflm-tiny-oz-latency \
  --gcc-bin "$GCC_BIN" --fvp "$FVP" --compare-int8
```

The current bundle records the pinned dependency revisions and source changes.
Local reproduction refuses to overwrite an existing bundle. The build command
without `--no-package` additionally packages its build artifacts and board scripts;
the published bundle also includes the subsequent simulator validation above.
