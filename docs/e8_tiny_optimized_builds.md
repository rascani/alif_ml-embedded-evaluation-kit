<!--
SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates <open-source-office@arm.com>
SPDX-License-Identifier: Apache-2.0
-->

# E8 Tiny size and latency profiles — 17 September 2026

**TFLM update:** [v3 INT8 registration results](e8_tflm_int8_registration_results.md)
supersede the TFLM v2 sizes below. This page preserves the generic-registration
baseline; the current TFLM builder enables INT8 selection. ET v5 is unchanged.

The new bundles are **ExecuTorch v5** and **TFLM v2**. Each contains all four models
in two profiles: logging disabled for flash accounting, and logging enabled for
new E8 latency/RAM measurements. No new board timings have been collected yet.
The [previous measured table](e8_tiny_current_summary.md) remains the historical
`-O3` result; its timings do not describe these new binaries.

## Compiler settings

Both profiles use GNU Arm 15.2.1, `-Oz -g -DNDEBUG` for the application, framework
core and framework operator wrappers, and `-O3` for CMSIS-NN 8.0.0 and CMSIS-DSP.
`-ffunction-sections` replaces `-fno-function-sections`; `-fdata-sections` and linker
`--gc-sections` remain enabled. There is no LTO. Debug information is kept in the
ELFs for analysis and is not stored in MRAM.

[CMSIS-NN's pinned documentation](../dependencies/cmsis-nn/README.md#compiler-options)
uses `-Ofast` by default, explicitly permits `CMSIS_OPTIMIZATION_LEVEL` overrides,
and warns against `-fno-builtin` and `-ffreestanding`. We retain the repository's
`-O3` choice rather than enabling additional floating-point relaxations. Both
frameworks use the same CMSIS-NN revision and effective flags. Builtins remain
available. CMSIS-DSP retains its existing `-ffast-math` setting; none of its
functions contribute to these inference images' filtered runtime/kernel totals.

TFLM's `KERNELS_OPTIMIZED_FOR_SPEED` implementation selection remains enabled,
including its persistent precomputed fully connected kernel sums. Its C++ wrappers
are compiled at `-Oz`; CMSIS-NN implementation files end with `-O3` in their actual
compiler command. ExecuTorch's upstream `EXECUTORCH_OPTIMIZE_SIZE` option is off
because that option appends `-Os`; our explicit release flags select `-Oz` instead.

Each image includes `compiler-audit.json`, which checks the effective last `-O`
option and function-section option, CMSIS builtins, and framework logging state
against the compilation database. The database includes configured translation
units, some of which are not retained by the linker. Maps and
`memory-attribution.json` account for the sections actually linked.

The profiles differ in `MLEK_LOG_ENABLE`, `HAL_LOG_ENABLE`, corresponding framework
logging definitions, and their firmware build ID. Silent TFLM builds define
`TF_LITE_STRIP_ERROR_STRINGS`; silent ExecuTorch builds use `ET_LOG_ENABLED=0`.
The benchmark batch and ET output-validation code remain configured in both.
Operator selection and ExecuTorch primitive selection remain enabled; the selected
primitive set is empty. Cortex-M operator runtime checks remain enabled.

## Flash with logging disabled

KiB means 1,024 bytes. Operators include framework implementations/utilities,
CMSIS-NN and the selected registry/resolver. Core includes framework execution,
allocation and planning. These are attribution totals, not complete standalone
firmware sizes.

| Model | Framework | Model (KiB) | Operators (KiB) | Core (KiB) | Total (KiB) |
| --- | --- | ---: | ---: | ---: | ---: |
| DS-CNN | TFLM | 52.67 | 66.27 | 10.30 | 129.25 |
| DS-CNN | ExecuTorch | 41.80 | 25.54 | 12.11 | 79.44 |
| ResNet8 | TFLM | 96.19 | 55.82 | 10.29 | 162.30 |
| ResNet8 | ExecuTorch | 93.65 | 17.71 | 12.11 | 123.46 |
| MobileNetV1 0.25 | TFLM | 325.48 | 66.27 | 10.30 | 402.05 |
| MobileNetV1 0.25 | ExecuTorch | 261.57 | 23.92 | 12.11 | 297.60 |
| Deep autoencoder | TFLM | 270.48 | 11.93 | 9.52 | 291.93 |
| Deep autoencoder | ExecuTorch | 273.41 | 2.86 | 12.11 | 288.37 |

ExecuTorch core is **12,398 bytes (12.11 KiB)** in every silent image, versus
39,188 bytes (38.27 KiB) in the previous logging-enabled `-O3` images. The new
logging-enabled core is **23,808 bytes (23.25 KiB)**. TFLM silent core ranges from
9,748 to 10,548 bytes (9.52–10.30 KiB); its logging-enabled core ranges from
11,030 to 11,870 bytes (10.77–11.59 KiB). The three changes were applied together;
these differences do not isolate the effect of logging, optimization or sections.

[Exact CSV](results/e8-tiny-oz-profiles-2026-09-17.csv) and
[JSON](results/e8-tiny-oz-profiles-2026-09-17.json) contain all 16 image records,
including separate kernel, CMSIS-NN and registry counts, full MRAM payload sizes,
and firmware/ELF hashes. Full MRAM includes platform, runner, diagnostics,
validation fixtures, adapter, shared toolchain/string pools and linker padding;
those categories are excluded from the table. Some shared support is required
for deployment. Merged strings and COMDAT ownership retain the earlier report's
attribution limitations. Duplicate TFLM archive member names are resolved using
source paths and input-section names in their compiled objects.

Model bytes, weights, memory placement, CPU clock, input generation and iteration
counts are unchanged. TFLM models use trained reference weights; the ET models
use untrained seed-23 weights and synthetic calibration. These are not matched-weight
accuracy comparisons. DS-CNN still has the pending internal DQ/Q pairs.

## Run on the Mac

Copy these archives and their `.sha256` files to `~/alif`:

- `build-e8-et-tiny-artifacts-v5.tar.gz`
- `build-e8-tflm-tiny-artifacts-v2.tar.gz`

For ExecuTorch:

```bash
cd ~/alif
shasum -a 256 -c build-e8-et-tiny-artifacts-v5.tar.gz.sha256
tar -xzf build-e8-et-tiny-artifacts-v5.tar.gz
cd build-e8-et-tiny-artifacts-v5
/usr/bin/python3 run.py verify
/usr/bin/python3 run.py run all
/usr/bin/python3 run.py collect
```

For TFLM:

```bash
cd ~/alif
shasum -a 256 -c build-e8-tflm-tiny-artifacts-v2.tar.gz.sha256
tar -xzf build-e8-tflm-tiny-artifacts-v2.tar.gz
cd build-e8-tflm-tiny-artifacts-v2
/usr/bin/python3 run.py verify
/usr/bin/python3 run.py run all
/usr/bin/python3 run.py collect
```

The included `run.py` uses the existing SE Tools installation and serial port.
Follow its SE/U4 switch prompts; reset three times per model, waiting for each
completion. It always flashes the **logging-enabled** image at `<model>/mram.bin`.
Silent images under `size/<model>/` are for size analysis and are not flashed by
this workflow. All capture, validation, summarization and result-collection scripts
are included. `collect` creates a timestamped results tar in the parent directory;
copy the two result archives back after finishing both suites.

Each boot performs one timed first inference, ten additional warm-ups and 100
measured inferences. ET also checks three saved int8 input/output pairs after the
benchmark. The parser now requires the firmware build ID as well as the model
hash, so old firmware with identical model weights is rejected. `results.csv` and
`results.json` retain latency-image flash fields and add explicitly named
`flash_size_build_*` fields for the separate silent image. Each model's nested
`size_build` manifest records its own hashes, sizes and artifact path.

New board latency and accounted inference RAM will be recorded after the rerun.
Initialization timing and TCM placement are outside this change. Accounted RAM
continues to exclude unused reservations, stack high-water usage, platform state
and transient initialization workspace; it is not a deployment-minimum RAM claim.

## Reproduce locally

From the repository root, with `GCC_BIN` pointing to the GNU Arm executable directory:

```bash
resources_downloaded/env/bin/python scripts/py/build_et_tiny.py \
  --gcc-bin "$GCC_BIN" --paired-profiles \
  --bundle-name build-e8-et-tiny-artifacts-v5 --no-package
resources_downloaded/env/bin/python scripts/py/build_tflm_tiny.py \
  --gcc-bin "$GCC_BIN" --paired-profiles \
  --bundle-name build-e8-tflm-tiny-artifacts-v2 --no-package
```

Use fresh bundle names/directories when repeating an experiment: the builders
refuse to overwrite existing bundles. Native TFLM tests and inference run for each
model. For Corstone-300 validation, set `FVP` to its executable and run:

```bash
resources_downloaded/env/bin/python scripts/py/validate_tiny_fvp.py \
  --bundle build-e8-et-tiny-artifacts-v5 --build build-e8-et-tiny-oz-latency \
  --gcc-bin "$GCC_BIN" --fvp "$FVP"
resources_downloaded/env/bin/python scripts/py/validate_tiny_fvp.py \
  --bundle build-e8-tflm-tiny-artifacts-v2 --build build-e8-tflm-tiny-oz-latency \
  --gcc-bin "$GCC_BIN" --fvp "$FVP"
```

This rebuilds each logged E8 image and requires an identical MRAM hash before
linking its inference libraries with Corstone startup and a semihosting timer.
The strict capture parser checks the resulting batch, memory accounting and ET
output validation. Simulator logs live under `validation/fvp/`; their cycle and
memory values are functional checks, not E8 measurements. Silent images receive
static build/flag/attribution checks; UART output validation uses their logged
counterparts. No ExecuTorch source-tree changes were needed for these profiles.

## Validation completed for these bundles

All **16 E8 images** build and pass static model/flag/flash checks. All **eight
logging-enabled images** were reproduced byte for byte and their inference archives
passed Corstone-300 execution with 111 benchmark invocations each. All 12 ET
reference-output comparisons passed. TFLM's four native unit-test/inference runs
passed. The 26 Python tests and PyLint 3.3.8 checks passed. The result-collection
archive was checked for expected contents and refusal to overwrite an existing file.
E8 hardware reruns remain pending; no simulator timing is included in the flash table.
