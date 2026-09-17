<!--
SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates <open-source-office@arm.com>
SPDX-License-Identifier: Apache-2.0
-->

# E8 ExecuTorch v6 — trained PTEs and DS-CNN Q/DQ cleanup

ExecuTorch v6 integrates the `mlperf-tiny-trained-qdq-cleanup.zip` export supplied
on 17 September 2026. All four PTEs use trained reference weights and differ from
the untrained PTEs used in our v5 firmware. Both redundant internal Q/DQ pairs are
removed from DS-CNN. The comparison partner remains **TFLM v3 with INT8 selection**.

**Board collection completed on 17 September:** all 12 ET boots and 12 saved-output
checks passed. The [current comparison](e8_tiny_current_summary.md) and
[collection report](e8_tiny_board_results_2026_09_17.md) record measured E8 latency and RAM.

The package contains four silent size images and four logged latency images,
using GCC 15.2.1, runtime/operator wrappers at `-Oz`, CMSIS-NN 8.0.0 at `-O3`,
function/data sections and linker garbage collection. Code/models remain in MRAM;
the method pool reserves 256 KiB in SRAM at `0x02000000`, the temporary pool reserves
64 KiB at `0x02040000`, and globals/heap/stack use DTCM. There is no NPU execution.
See the preserved [CMSIS-NN compiler guidance](../dependencies/cmsis-nn/README.md#compiler-options).

## Export changes

| Model | Prior v5 PTE bytes | New v6 PTE bytes | Prior planned tensor bytes | New planned tensor bytes | New operator calls |
| --- | ---: | ---: | ---: | ---: | ---: |
| DS-CNN | 42,800 | 42,416 | 40,000 | 20,464 | 12 |
| ResNet8 | 95,896 | 96,152 | 49,728 | 49,728 | 15 |
| MobileNetV1 0.25 | 267,848 | 270,792 | 73,728 | 73,728 | 30 |
| Deep autoencoder | 279,968 | 279,968 | 768 | 768 | 10 |

The autoencoder has the same file size but different weights and SHA256. All four
have INT8 inputs/outputs; the classifiers retain quantized softmax. Our deserialized
PTE audit confirms the operator counts, planned sizes, zero delegates and zero
primitive or Q/DQ calls in every `forward` graph.

The producer's cleanup-only comparison used an intermediate **trained** DS-CNN
baseline of 43,696 bytes, not our untrained v5 PTE. Against that baseline, cleanup
saves 1,280 PTE bytes, four operator calls and 19,536 planned tensor bytes. The other
three trained PTEs are byte-identical to the producer's pre-cleanup trained exports.
Our v5-to-v6 changes include both the trained weights/requantization and Q/DQ cleanup.

The producer reports broad native validation and unchanged quality after cleanup.
Reported scores are DS-CNN 92.1677% accuracy, ResNet8 87.00%, VWW 85.60%, and AD
0.841005 macro AUC. AD remains below its 0.85 target. These are producer-supplied
quality results, not a new accuracy evaluation of the E8 firmware. Both frameworks
now derive from trained reference weights, with different quantization/calibration
and potentially different preprocessing contracts; this is not an identical-byte
model or quantization comparison.

## Flash with logging disabled

KiB means 1,024 bytes. Operators include framework kernels/utilities, CMSIS-NN and
selected registry/resolver. Core is execution/allocation/planning. The total excludes
runner, diagnostics, platform, validation fixtures, adapters, shared toolchain/string
pools, linker tables and padding. It is not complete deployable MRAM size.

| Model | Framework | Model KiB | Operators KiB | Core KiB | Total KiB |
| --- | --- | ---: | ---: | ---: | ---: |
| DS-CNN | TFLM v3 | 52.67 | 30.58 | 10.30 | 93.55 |
| DS-CNN | ExecuTorch v6 | 41.42 | 23.92 | 12.11 | 77.45 |
| ResNet8 | TFLM v3 | 96.19 | 25.46 | 10.29 | 131.94 |
| ResNet8 | ExecuTorch v6 | 93.90 | 17.71 | 12.11 | 123.71 |
| MobileNetV1 0.25 | TFLM v3 | 325.48 | 30.58 | 10.30 | 366.36 |
| MobileNetV1 0.25 | ExecuTorch v6 | 264.45 | 23.92 | 12.11 | 300.47 |
| Deep autoencoder | TFLM v3 | 270.48 | 7.79 | 9.52 | 287.79 |
| Deep autoencoder | ExecuTorch v6 | 273.41 | 2.86 | 12.11 | 288.37 |

[Exact CSV](results/e8-tiny-trained-qdq-2026-09-17.csv) and
[JSON](results/e8-tiny-trained-qdq-2026-09-17.json) contain all 16 current images,
both logging profiles, individual kernel/CMSIS-NN/registry byte counts, complete
MRAM sizes and model/firmware/ELF hashes. ET silent core remains 12,398 bytes and
logged core remains 23,808 bytes. DS-CNN operator flash falls by 1,656 bytes versus
v5; the other ET operator totals are unchanged. Earlier CSV/JSON files remain intact.

## Validation and measurement scope

All eight E8 images pass compiler and flash attribution checks. The logged E8
images are rebuilt and required to match their frozen MRAM hashes before linking
their inference libraries to a Corstone-300 Cortex-M55 harness. Each model completes
111 benchmark invocations plus an untimed exact native-output check. Simulator logs,
PTE/selection audits and `validation/fvp/checks.json` are included in the package.
Silent images receive static checks; execution checks use their logged counterparts.

The new ZIP supplies **one saved native input/output pair per model**. Each boot
validates that pair and logs `reference=cortex_m_native_int8`. The sample indices
are DS-CNN 0, ResNet8 7657, VWW 0 and AD 0 in the producer's datasets. This replaces
the old package's three synthetic Python-reference pairs. Full validation datasets
are not embedded. The binary-to-NumPy conversion preserves every signed byte;
both original example files and converted fixture hashes are recorded. Fixtures
remain outside the filtered model/operators/core flash totals.

The runner prints the reference identity from its generated fixture header, and
the capture parser requires the reference and count in the manifest. It still
requires the model hash and firmware build ID, so old firmware cannot pass as v6.
The 34 Python tests cover old/new reference handling, import checksums, fixture
conversion, sample-count consistency and the existing benchmark accounting.

The ET runtime checkout remains at staged tree
`0510beb4b48b8785477a3c11b23c5bc18bd7841a`. Its 902 tracked runtime/kernel/schema/
Cortex-M operator/runner-utility files match the exporter's source checkout exactly;
the unused Eigen submodule is excluded from this file comparison. The exporter's
new commit `3879104b78aa01678e7711f68e8da0e834f1f6f2` changes shared export passes,
not these runtime files. No ET source-tree edit was needed. Operator and primitive
selection remain enabled; the primitive set is empty and inputs use planned storage
directly. The full incoming ZIP and provenance are preserved under `export/`.

E8 collection now confirms all four simulator RAM totals below, with stable values
across three boots per model. Accounted inference RAM includes used method/planned
storage, temporary inference peak, outside persistent objects/heap and attributed
runtime static storage. It excludes unused reservations, stack high water,
initialization workspace and benchmark/platform/reporting memory. The new measured
timings are in the linked collection report; original timings remain attached to
the earlier untrained ET and generic TFLM builds.

ET inference RAM confirmed on both simulator and E8 (bytes):

| Model | Planned tensors | Method metadata | Temporary invoke peak | Outside persistent | Runtime static | Accounted total |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| DS-CNN | 20,464 | 8,008 | 0 | 808 | 300 | 29,580 |
| ResNet8 | 49,728 | 8,920 | 0 | 808 | 288 | 59,744 |
| MobileNetV1 0.25 | 73,728 | 21,588 | 0 | 808 | 288 | 96,412 |
| Deep autoencoder | 768 | 4,480 | 0 | 808 | 192 | 6,248 |

The prior v5 simulator total for DS-CNN was 49,916 bytes. The new result is 20,336
bytes lower: 19,536 from planned tensors, 752 from method metadata and 48 from
runtime static storage. The other models' accounted totals are unchanged. These
values are now confirmed on E8 and included in the current board-result table.

## Run on the Mac

Copy `build-e8-et-tiny-artifacts-v6.tar.gz` and its `.sha256` file to `~/alif`.
The TFLM partner is the already prepared `build-e8-tflm-tiny-artifacts-v3.tar.gz`.
All flashing, capture, parsing and collection scripts are included.

```bash
cd ~/alif
shasum -a 256 -c build-e8-et-tiny-artifacts-v6.tar.gz.sha256
tar -xzf build-e8-et-tiny-artifacts-v6.tar.gz
cd build-e8-et-tiny-artifacts-v6
/usr/bin/python3 run.py verify
/usr/bin/python3 run.py run all
/usr/bin/python3 run.py collect
```

The script uses the established SE Tools installation and serial port. Follow its
SE/U4 switch prompts and reset three times per model, waiting for completion. It
flashes the logged `<model>/mram.bin`; silent `size/<model>/mram.bin` files are for
size accounting. Each boot separately times the first call, runs ten warm-ups and
100 measured calls, then checks the saved native example. Input filling, reporting
and output validation are outside the measured inference interval.

Repeat the suite in the existing TFLM v3 directory:

```bash
cd ~/alif/build-e8-tflm-tiny-artifacts-v3
/usr/bin/python3 run.py verify
/usr/bin/python3 run.py run all
/usr/bin/python3 run.py collect
```

Each `collect` command creates a timestamped result tar in the parent directory;
copy both results archives back. There is no need to flash the silent profiles.

## Reproduce the import and builds

Set `EXPORT_ZIP` to the supplied trained Q/DQ-cleanup ZIP, `GCC_BIN` to the GNU Arm
toolchain directory and `FVP` to the Corstone-300 executable. Use fresh output and
bundle names when repeating an experiment; existing artifacts are not overwritten.

```bash
resources_downloaded/env/bin/python scripts/py/import_et_tiny_bundle.py \
  --archive "$EXPORT_ZIP" \
  --output resources_downloaded/et_tiny/mlperf-tiny-trained-qdq-cleanup
resources_downloaded/env/bin/python scripts/py/build_et_tiny.py \
  --gcc-bin "$GCC_BIN" --jobs 8 --paired-profiles \
  --export-dir resources_downloaded/et_tiny/mlperf-tiny-trained-qdq-cleanup \
  --bundle-name build-e8-et-tiny-artifacts-v6 --no-package
resources_downloaded/env/bin/python scripts/py/validate_tiny_fvp.py \
  --bundle build-e8-et-tiny-artifacts-v6 --build build-e8-et-tiny-oz-latency \
  --gcc-bin "$GCC_BIN" --fvp "$FVP"
```

The importer verifies the entire ZIP checksum inventory, PTE identities and example
tensor sizes. The builder verifies the normalized export and pinned runtime tree,
generates model-specific selection and captures both optimization profiles. The
published archive adds final validation evidence, this report, current flash CSV/JSON,
board scripts and SHA256 inventories after those checks complete.
