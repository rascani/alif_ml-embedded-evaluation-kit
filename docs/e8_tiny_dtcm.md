<!--
SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates <open-source-office@arm.com>
SPDX-License-Identifier: Apache-2.0
-->

# E8 HP DTCM inference-pool experiment

These bundles move the inference pools from SRAM to local DTCM on the E8
Cortex-M55-HP. They retain the ET v6 / TFLM v3 models, full pool reservations,
GCC 15.2.1, runtime/operator `-Oz`, CMSIS-NN 8.0.0 `-O3`, CPU-only execution,
operator selection, and empty ET primitive selection. TFLM keeps compatible
INT8 registrations. ET retains the trained DS-CNN export with its Q/DQ cleanup.
Integer-constant deduplication is not included.

| Allocation | Previous SRAM address | New local DTCM address | Reserved |
| --- | --- | --- | ---: |
| TFLM tensor arena | `0x02000000` | `0x20020000` | 256 KiB |
| ET method pool, including planned activations | `0x02000000` | `0x20020000` | 256 KiB |
| ET temporary pool | `0x02040000` | `0x20060000` | 64 KiB |

HP has 1 MiB DTCM at `0x20000000–0x200FFFFF`. The first 128 KiB remains
available for the existing globals and 64 KiB heap; the 32 KiB stack remains at
`0x200F8000`. Neither framework's reservations approach the stack. Code, model
weights and validation fixtures remain in MRAM. The same MPU setup remains in
use; local TCM accesses bypass caches.

| Logged builds | Total DTCM reserved, including pools/globals/heap/stack | DTCM unallocated |
| --- | ---: | ---: |
| TFLM, all four models | 368,536 B (359.90 KiB) | 680,040 B (664.10 KiB) |
| ET, depending on model | 434,288–434,392 B (424.11–424.21 KiB) | 614,184–614,288 B (599.79–599.89 KiB) |

These are static deployment reservations, not measured inference RAM usage.
The unallocated total includes gaps and is not one contiguous allocation.

The GCC linker variant is `RTSS-HP-infrun-dtcm`. It explicitly collects both
pool input sections in `.bss.inference` and uses the otherwise-empty ITCM BSS
entry in the startup zero table. This preserves the table size and MRAM code
alignment; an assertion requires ITCM BSS to remain empty. Link-time assertions
reject heap/stack collisions and region overflow. Per-image
`inference-memory.json` verifies the ELF pool symbols,
sizes, startup zero table and DTCM reservations. `sections.json`, the ELF and
linker map remain included for inspection.

All 16 images preserve their baseline model bytes and filtered model/operator/core
flash counts. Globals, heap, stack, zero-table size, and MRAM read-only section
base addresses also match the corresponding SRAM builds. Firmware identities and
pool address relocations differ. The [exact CSV](results/e8-tiny-dtcm-builds-2026-09-17.csv)
and [JSON audit](results/e8-tiny-dtcm-builds-2026-09-17.json) record hashes and placement.

Each bundle contains four logged latency images under `kws`, `ic`, `vww`, and
`ad`, plus four logging-disabled size images under `size`. The included runner
flashes logged images. Each boot records a separate first inference, ten warmups
and 100 measured inferences. ET also checks its saved native INT8 output after
timing. Three boots per model are requested. Unique firmware build IDs prevent
mixing results with the SRAM bundles.

## Run on the Mac

Copy both archives and their `.sha256` sidecars to `~/alif`. For TFLM:

```bash
cd ~/alif
shasum -a 256 -c build-e8-tflm-tiny-artifacts-v4-dtcm.tar.gz.sha256
tar -xzf build-e8-tflm-tiny-artifacts-v4-dtcm.tar.gz
cd build-e8-tflm-tiny-artifacts-v4-dtcm
/usr/bin/python3 run.py verify
/usr/bin/python3 run.py run all
/usr/bin/python3 run.py collect
```

For ExecuTorch:

```bash
cd ~/alif
shasum -a 256 -c build-e8-et-tiny-artifacts-v7-dtcm.tar.gz.sha256
tar -xzf build-e8-et-tiny-artifacts-v7-dtcm.tar.gz
cd build-e8-et-tiny-artifacts-v7-dtcm
/usr/bin/python3 run.py verify
/usr/bin/python3 run.py run all
/usr/bin/python3 run.py collect
```

The scripts default to `/Users/rja/app-release-exec-macos` and
`/dev/cu.usbmodem0012192765291`. Follow the SE/U4 prompts, resetting three times
per model and waiting for each completion. Copy the two result tarballs printed
by `collect` back to this repository's `build-artifacts` directory.

## Rebuild

From the repository root with the existing prepared dependencies and Python environment:

```bash
GCC_BIN=/home/rja/executorch/examples/arm/arm-scratch/arm-gnu-toolchain-15.2.rel1-x86_64-arm-none-eabi/bin
resources_downloaded/env/bin/python scripts/py/build_tflm_tiny.py \
  --gcc-bin "$GCC_BIN" --paired-profiles --inference-memory dtcm \
  --bundle-name build-e8-tflm-tiny-artifacts-v4-dtcm
resources_downloaded/env/bin/python scripts/py/build_et_tiny.py \
  --gcc-bin "$GCC_BIN" --paired-profiles --inference-memory dtcm \
  --export-dir resources_downloaded/et_tiny/mlperf-tiny-trained-qdq-cleanup \
  --bundle-name build-e8-et-tiny-artifacts-v7-dtcm
```

Choose new bundle names when directories already exist; builders refuse to
overwrite experiments. DTCM builds use separate build trees. The default
`--inference-memory sram` preserves the original linker layout.

Hardware collection is complete: all 24 selected boots and 12 ET output checks
passed. See the [SRAM versus DTCM results](e8_tiny_dtcm_results_2026_09_17.md) for
latency improvements and unchanged accounted RAM/filtered flash. The build-time
CSV/JSON audit above remains a preserved pre-collection snapshot.

Included Corstone validation is functional testing of the inference libraries,
not validation of E8 TCM behavior or performance. Each bundle's
`validation/fvp/checks.json` records functional checks and byte-for-byte firmware
reproduction. `validation/linker-guards/checks.json` records successful rejection
of deliberately overlapping or overflowing layouts. The bundled `reference`
directory preserves the prior SRAM measurement summary and exact comparison.
