<!--
SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates <open-source-office@arm.com>
SPDX-License-Identifier: Apache-2.0
-->

# E8 ExecuTorch v8 — integer pooling, SRAM inference pools

This bundle uses the four trained PTEs from `mlperf-tiny-trained-integer-pooling.zip`.
It keeps the SRAM configuration and compiler settings of ET v6. Integer and integer-list
pooling reduces serialized model size and method metadata without changing tensor
placement, weights or operator calls. **E8 collection completed on 17 September:**
all 12 selected boots and saved-output checks pass, confirming every simulator RAM
total below. The [board analysis](e8_et_tiny_v8_results.md) records the measured latency
and deltas; the [current comparison](e8_tiny_current_summary.md) now uses ET v8 versus TFLM v3.

## Configuration and validation

The package contains four logged latency images and four silent size images for
the E8 Cortex-M55-HP, CPU-only at 400 MHz. GCC 15.2.1 compiles runtime/operator
wrappers at `-Oz` and CMSIS-NN 8.0.0 at `-O3`, with function/data sections, linker
garbage collection and no LTO. See the preserved
[CMSIS-NN guidance](../dependencies/cmsis-nn/README.md#compiler-options).

All eight images have the following inference pools, verified from linker symbols
and the startup zero table:

| Storage | Location | Reserved bytes |
| --- | --- | ---: |
| Method pool, including planned tensors | SRAM `0x02000000` | 262,144 |
| Temporary pool | SRAM `0x02040000` | 65,536 |
| Code and serialized model | MRAM | Per-image totals below |
| Globals, heap and stack | DTCM | 64 KiB heap and 32 KiB stack, plus globals |

The runtime source tree is unchanged at
`0510beb4b48b8785477a3c11b23c5bc18bd7841a`. The exporter's commit
`ae64c3c72e31445f3243f5e7811ab97b76ad27ca` changes the emitter and its tests relative
to the previous exporter. No runtime change was needed. Operator and primitive
selection stay enabled; no primitive registrations are selected. Inputs continue
to use planned tensor storage directly.

We reran the supplied PTE comparison script against our frozen v6 export. It confirms
identical weights, tensor metadata/planned offsets, operators, input/output contracts,
graphs and equivalent instruction arguments after constant indices are remapped.
All eight images pass compiler, placement and flash attribution checks. Their
operator selections match v6, apart from the source path in selection debug metadata.

Each logged E8 image was rebuilt byte-for-byte before its inference libraries were
linked into the Corstone-300 Cortex-M55 harness. All four complete 111 benchmark
invocations and an exact saved native-output check. Each model embeds sample 0;
ResNet8 previously used sample 7657. The raw example bytes are preserved in the
converted fixtures. Output checks and synthetic input preparation are outside timing.
Silent images receive static checks; execution checks use the logged counterparts.

The archive includes the original export and checksum inventory under `export/`,
the rerun PTE audit at `validation/pte-comparison.json`, and simulator logs/checks at
`validation/fvp/`. These checks establish functionality and allocator counts, not E8
latency. Producer-supplied dataset validation remains separate from our one-example
firmware checks. The benchmark is not an official MLPerf result.

## Model and RAM savings

All values below are bytes. Old RAM is the measured v6 E8 result; new RAM was first
measured in the Corstone harness and is now confirmed on E8 across all three boots. The savings are entirely in method metadata; planned tensors,
inference temporary peak, outside persistent state and runtime static storage are unchanged.

| Model | Old PTE | New PTE | PTE saved | Old metadata | New metadata | RAM saved | Old accounted RAM | New accounted RAM, E8 confirmed |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| DS-CNN | 42,416 | 38,576 | 3,840 | 8,008 | 5,056 | 2,952 | 29,580 | 26,628 |
| ResNet8 | 96,152 | 91,928 | 4,224 | 8,920 | 5,640 | 3,280 | 59,744 | 56,464 |
| MobileNetV1 0.25 | 270,792 | 259,144 | 11,648 | 21,588 | 12,372 | 9,216 | 96,412 | 87,196 |
| Deep autoencoder | 279,968 | 278,560 | 1,408 | 4,480 | 3,552 | 928 | 6,248 | 5,320 |

| Model | Planned tensors | Method metadata | Inference temp peak | Outside persistent | Runtime static | Accounted RAM, E8 confirmed |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| DS-CNN | 20,464 | 5,056 | 0 | 808 | 300 | 26,628 |
| ResNet8 | 49,728 | 5,640 | 0 | 808 | 288 | 56,464 |
| MobileNetV1 0.25 | 73,728 | 12,372 | 0 | 808 | 288 | 87,196 |
| Deep autoencoder | 768 | 3,552 | 0 | 808 | 192 | 5,320 |

Accounted RAM excludes unused pool reservations, stack high water, initialization
workspace, transient heap peaks and benchmark/platform/reporting memory. The
256 KiB + 64 KiB SRAM reservations remain unchanged; these savings reduce used
storage within the method pool. No RAM or latency measurement is claimed for the
silent images.

## Flash breakdown

The kernel, CMSIS-NN, registry and runtime-core byte counts are unchanged from v6
in both profiles. Therefore the filtered flash saving equals the PTE size saving.
Operators comprise framework kernels/utilities, CMSIS-NN and the selected registry.
Core covers execution, allocation and planning. Filtered total sums model, operators
and core; it excludes runner, diagnostics, validation fixtures, platform, MLEK adapters,
shared toolchain/string pools and linker tables/padding. Full MRAM is the deployable
binary size including those costs.

| Model | Logging | Model bytes | Operators bytes | Core bytes | Filtered total bytes | Full MRAM bytes |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| DS-CNN | Disabled | 38,576 | 24,494 | 12,398 | 75,468 | 203,668 |
| DS-CNN | Enabled | 38,576 | 28,222 | 23,808 | 90,606 | 245,220 |
| ResNet8 | Disabled | 91,928 | 18,132 | 12,398 | 122,458 | 253,212 |
| ResNet8 | Enabled | 91,928 | 21,794 | 23,808 | 137,530 | 294,476 |
| MobileNetV1 0.25 | Disabled | 259,144 | 24,494 | 12,398 | 296,036 | 451,388 |
| MobileNetV1 0.25 | Enabled | 259,144 | 28,222 | 23,808 | 311,174 | 492,940 |
| Deep autoencoder | Disabled | 278,560 | 2,924 | 12,398 | 293,882 | 421,700 |
| Deep autoencoder | Enabled | 278,560 | 4,040 | 23,808 | 306,408 | 457,124 |

[Exact CSV](results/e8-et-tiny-integer-pooling-2026-09-17.csv) and
[JSON](results/e8-et-tiny-integer-pooling-2026-09-17.json) record all eight images,
individual kernel/CMSIS-NN/registry counts, allocator evidence and firmware hashes
at build time. Their pending board fields are preserved as build provenance; the
[completed collection](e8_et_tiny_v8_results.md) records actual E8 measurements.
Changes in MRAM layout and method metadata can affect caches even though the
operators and tensor plan are unchanged.

## Run on the Mac

Copy `build-e8-et-tiny-artifacts-v8-sram-integer-pooling.tar.gz` and its `.sha256`
file to `~/alif`. All flashing, capture, parsing and collection scripts are included.

```bash
cd ~/alif
shasum -a 256 -c build-e8-et-tiny-artifacts-v8-sram-integer-pooling.tar.gz.sha256
tar -xzf build-e8-et-tiny-artifacts-v8-sram-integer-pooling.tar.gz
cd build-e8-et-tiny-artifacts-v8-sram-integer-pooling
/usr/bin/python3 run.py verify
/usr/bin/python3 run.py run all
/usr/bin/python3 run.py collect
```

Follow the SE/U4 switch prompts. Reset three times per model and wait for completion
after each reset. The script uses the existing SE Tools installation and serial port.
It flashes the logged `<model>/mram.bin`; `size/<model>/mram.bin` is only for size
accounting. Each boot times the first call, runs ten warm-ups and 100 measured calls,
then checks its saved native example. The build ID and model SHA256 prevent stale
images from being accepted as this experiment.

`collect` prints the path of a timestamped results tar beside the extracted bundle.
Copy that results tar back to `build-artifacts`. The existing SRAM TFLM v3 result
remains the comparison partner; this export update does not require a TFLM rebuild.

## Reproduce the firmware and validation

Set `EXPORT_ZIP` to the supplied integer-pooling ZIP, `GCC_BIN` to the GCC toolchain
binary directory and `FVP` to the Corstone-300 executable. Use fresh import/bundle
names when repeating the experiment; existing exports and bundles are not overwritten.

```bash
resources_downloaded/env/bin/python scripts/py/import_et_tiny_bundle.py \
  --archive "$EXPORT_ZIP" \
  --output resources_downloaded/et_tiny/mlperf-tiny-trained-integer-pooling
resources_downloaded/env/bin/python scripts/py/build_et_tiny.py \
  --gcc-bin "$GCC_BIN" --jobs 8 --paired-profiles --inference-memory sram \
  --export-dir resources_downloaded/et_tiny/mlperf-tiny-trained-integer-pooling \
  --bundle-name build-e8-et-tiny-artifacts-v8-sram-integer-pooling --no-package
resources_downloaded/env/bin/python scripts/py/validate_tiny_fvp.py \
  --bundle build-e8-et-tiny-artifacts-v8-sram-integer-pooling \
  --build build-e8-et-tiny-oz-latency --gcc-bin "$GCC_BIN" --fvp "$FVP" --jobs 8
```

The published archive adds this report, exact CSV/JSON, the PTE comparison, final
validation evidence and host scripts after those checks. Its manifest records
the export ZIP SHA256, firmware source revision, runtime tree, dependencies and
compiler/placement audits. The original v6 SRAM and v7 DTCM artifacts are preserved.
