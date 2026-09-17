<!--
SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates <open-source-office@arm.com>
SPDX-License-Identifier: Apache-2.0
-->

# E8 selective builds: Bloaty comparison

This is the preserved logging-on baseline. See the
[logging and primitive-selection experiment](e8_logging_prim_comparison.md) for the
updated measurements and configuration.

Measured on 2026-09-15 using the ELFs in `build-e8-cpu-both-selective-artifacts/`.
Both target M55-HP, CPU-only, GCC `-O3`, and CMSIS-NN 8.0.0, with model-specific
operator selection enabled. Bloaty 1.1 was built from commit
`37bf8e708398727b58d9a61e66e9ccb5db6df619`.

**Excluding embedded model bytes, ExecuTorch's image is 25.4 KiB larger.** The
models and their operator requirements differ, so this does not establish the
relative footprint for an equivalent MLPerf Tiny workload.

| MRAM footprint | ExecuTorch | TFLM | ET minus TFLM |
| --- | ---: | ---: | ---: |
| Complete application image | 282.41 KiB | 336.24 KiB | -53.83 KiB |
| Embedded model | 2.97 KiB | 82.22 KiB | -79.25 KiB |
| Image excluding model | 279.44 KiB | 254.02 KiB | +25.42 KiB |

The exact application payload sizes are 289,188 and 344,308 bytes. These exclude
ELF debug information and file-container overhead.

## Where the image space goes

The table below groups Bloaty's compile-unit attribution across the sections stored
in MRAM, including the initial values copied into DTCM. Model bytes come from the
embedded ELF objects. The final row includes bytes Bloaty cannot attribute to a
compile unit, after separating the models, plus image alignment. These categories
reconcile exactly to the application images before rounding.

| Attributed component | ExecuTorch | TFLM | ET minus TFLM |
| --- | ---: | ---: | ---: |
| Embedded model | 2.97 KiB | 82.22 KiB | -79.25 KiB |
| Framework runtime and schema helpers | 40.26 KiB | 16.02 KiB | +24.24 KiB |
| Operator kernels and CMSIS-NN | 5.65 KiB | 33.01 KiB | -27.36 KiB |
| ET primitive operators | 9.02 KiB | — | +9.02 KiB |
| ET generated registrations | 1.60 KiB | — | +1.60 KiB |
| Framework adapter (`EtModel`/`TflmModel`, tensors, etc.) | 10.50 KiB | 6.20 KiB | +4.30 KiB |
| Application and platform | 91.62 KiB | 93.50 KiB | -1.89 KiB |
| Other / no compile-unit attribution / padding | 120.79 KiB | 105.29 KiB | +15.50 KiB |

These are attribution groups, not independently removable libraries. TFLM's generated
registration code is inline in `MainLoop` and counted under application code. The
unattributed bucket includes toolchain code and read-only data, including strings;
it must not be interpreted as entirely framework overhead. Bloaty's symbol view
identifies many contributors in that bucket even when compile-unit information is absent.

Notable source-file contributions to `.readonly.at_mram`:

- ET `runtime/executor/method.cpp`: 17.4 KiB; `program.cpp`: 5.85 KiB;
  `method_meta.cpp`: 4.18 KiB.
- ET `register_prim_ops.cpp`: 6.70 KiB of code/read-only data. The full primitive
  group, including implementations and initialized registrations, is 9.02 KiB.
  This build retains all 28 runtime primitives alongside the three model operators.
- The application's ET adapter `EtModel.cc`: 9.50 KiB; TFLM's `TflmModel.cc`: 5.61 KiB.
- TFLM `micro_allocator.cc`: 3.75 KiB; `micro_allocation_info.cc`: 2.43 KiB;
  `greedy_memory_planner.cc`: 2.10 KiB.
- CMSIS-NN contributes 1.52 KiB to ET and 22.69 KiB to TFLM. TFLM includes softmax;
  the ET smoke model does not. TFLM's generic numeric dispatch also retains int4
  and int16 fully-connected helpers alongside int8 support.

## Shared overhead worth investigating

Both images contain the following large symbols. Their sizes are identical in
the Bloaty reports and therefore mostly cancel in the differential view.

| Symbol | Bytes in each image |
| --- | ---: |
| `d_print_comp_inner` (C++ demangler) | 11,884 |
| `_vfprintf_r` | 8,484 |
| `_svfprintf_r` | 8,208 |
| `_vfiprintf_r` | 4,524 |
| `_dtoa_r` | 3,596 |
| `arm::app::Profiler::UpdateRunningStats()` | 3,084 |

Demangler and verbose-termination symbols account for about **31.1 KiB per image**
(the `d_*`, `cplus_demangle*`, `__cxa_demangle`, and verbose-handler symbol group).
The four formatting/conversion routines above alone account for **24.2 KiB**;
other stdio support is additional.

The linker maps show the retention path from `Main.cc`'s `std::terminate()` reference
through `eh_terminate.o`, `vterminate.o`, and `cp-demangle.o`. Disabling exceptions
in application compilation does not by itself remove this prebuilt library code.

Platform drivers are also significant: Bloaty attributes 30.5 KiB to `Driver_IO.c`
and 13.1 KiB to `Driver_USART.c` in each image. Those figures include attributed
read-only data and are not estimates of removable code.

Candidate follow-ups, without changing the measured binaries:

1. Investigate a small embedded termination path and reduced formatting support
   for both frameworks, while retaining the diagnostics needed for benchmarking.
2. Select ET runtime primitives from the model as well as ordinary operators.
3. For TFLM, investigate the available CMSIS-NN `Register_FULLY_CONNECTED_INT8`
   and `Register_SOFTMAX_INT8` entry points for models whose tensor types match.
   Current selection is by operator, not numeric variant. Validate outputs and
   inspect the resulting link before claiming a saving.
4. Re-run this comparison using equivalent Tiny model pairs. The current model
   and softmax differences are large enough to obscure framework-level conclusions.

## Method and reproduction

Bloaty's `--domain=vm` excludes debug-only bytes from the displayed sizes.
Its whole-ELF VM total includes RAM reservations as well as MRAM, so it is **not**
the application payload size. For the firmware comparison, reports filter these
stored sections:

```text
.readonly.at_mram
.startup.at_mram
.copy.table.at_mram
.zero.table.at_mram
.data.dtcm.at_mram
```

The selected sections sum to 289,172 bytes for ET and 344,300 for TFLM. Adding
16 and 8 bytes of MRAM alignment, respectively, reproduces the raw image lengths.
Model object sizes are 3,040 and 84,192 bytes. Bloaty's symbol attribution can also
include nearby literal/reference bytes, so those exact object sizes are used for
model subtraction rather than the slightly larger Bloaty symbol rows.

Run from the repository root:

```bash
build-artifacts/tools/bloaty-build/bloaty \
  --domain=vm -s vm -w -n 30 -d sections,symbols \
  --source-filter='^\.(readonly|startup|copy\.table|zero\.table|data\.dtcm)\.at_mram$' \
  build-e8-cpu-both-selective-artifacts/et/mlek_inference_runner.axf -- \
  build-e8-cpu-both-selective-artifacts/tflm/mlek_inference_runner.axf
```

Positive differences mean **ET is larger**. Substitute `sections,compileunits`
to compare source files. Full output and reproduction details are in
`build-artifacts/bloaty-comparison/`:

- `et-minus-tflm-mram-symbols.txt` and `.csv`: symbol differences.
- `et-minus-tflm-mram-compileunits.txt` and `.csv`: source-file differences.
- `et-*` and `tflm-*`: individual section, symbol, and source-file reports.
- `components.bloaty`: compile-unit grouping rules.
- `summary.csv` and `summary.json`: reconciled component totals in bytes.
- `manifest.json`: tool revision and input ELF/image hashes.
- `commands.sh`: commands to regenerate all raw Bloaty reports.

All CSV reports use unlimited rows. Text symbol/source reports display the largest
30 rows per section, with remaining contributions collapsed. Both ELFs' DWARF data
were read successfully; the `[section ...]` entries indicate incomplete source
attribution, not additional model-independent runtime measurements.
