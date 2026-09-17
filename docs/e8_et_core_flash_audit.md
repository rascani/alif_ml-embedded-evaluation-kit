<!--
SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates <open-source-office@arm.com>
SPDX-License-Identifier: Apache-2.0
-->

# ExecuTorch core flash audit — 17 September 2026

The [paired profile builds](e8_tiny_optimized_builds.md) now apply function sections,
`-Oz` outside CMSIS, and separate logging-off size images across both frameworks.
ET core is 12.11 KiB with logging off and 23.25 KiB with logging on in those builds.
The experiments below remain the earlier isolated investigation.

The published 38.27 KiB ET core is the actual retained size of the benchmark firmware,
but its GCC configuration prevents unused functions from being removed individually.
An isolated ResNet8 link experiment reduces core flash to 31.42 KiB with function
sections, and to 23.36 KiB with function sections plus size optimization of the runtime
archives. Numerical kernels retain `-O3`, logging remains enabled, and the original
firmware, PTEs, runtime sources and E8 measurements are unchanged.

## Cause

`scripts/cmake/toolchains/bare-metal-gcc.cmake:95` supplies `-fno-function-sections`.
ET requests `-ffunction-sections` earlier, but the later negative option wins. The
resulting `method.cpp`, `method_meta.cpp`, `program.cpp` and other objects contain
large monolithic `.text` sections. Although linking uses `--gc-sections`, referencing
one function retains other functions in that same section.

The flag predates this benchmark: commit `f0ff690f5746f5237ff765d8792d8568c7a190d3`
changed it while fixing GCC compilation after an upstream merge. The commit gives
no more specific reason. The flag also appears in the TFLM build; an equivalent TFLM
size experiment has not been run. It should be corrected and validated for both
frameworks before publishing another measured comparison.

## Controlled size experiment

Only `libexecutorch_core.a` and `libexecutorch.a` were recompiled. All other linked
objects/libraries, compiler version, model, selection headers, logging and checks were
held fixed. The baseline relink reproduces the frozen v4 IC MRAM payload byte-for-byte.
The core definition matches the shareable table: it excludes operators/CMSIS-NN,
resolver/registry, dedicated logging objects, shared strings, adapter, platform and
benchmark code. Inline checks in retained runtime functions remain included.

| Configuration | Core text (B) | Core other data (B) | Core total (B) | Core (KiB) | Full MRAM image (B) |
| --- | ---: | ---: | ---: | ---: | ---: |
| Published v4: `-O3`, function sections disabled | 38,544 | 644 | 39,188 | 38.27 | 396,876 |
| `-O3`, function sections enabled for runtime archives | 31,532 | 644 | 32,176 | 31.42 | 387,260 |
| Runtime archives `-Os`, function sections enabled | 23,570 | 348 | 23,918 | 23.36 | 379,292 |

Function sections alone remove 7,012 core bytes. Examples of no-longer-retained APIs
include output/attribute tensor metadata, external output-buffer setters, bulk input
accessors, and unused layout helpers. The change reduces `method.cpp` by 2,540 B,
`method_meta.cpp` by 2,412 B, and tensor utilities by 1,208 B. Core-only size optimization
then saves another 8,258 core bytes. Full-image savings also include shared strings and
other support, so they differ from the core-only deltas.

The original core's source-file contributions are:

| Component | Bytes |
| --- | ---: |
| Method loading/execution (`method.cpp`) | 18,064 |
| Program loading (`program.cpp`) | 5,992 |
| Method metadata (`method_meta.cpp`) | 4,396 |
| Tensor deserialization (two source files) | 5,284 |
| Tensor implementation/utilities | 3,860 |
| Data map, backend interface, headers and other helpers | 1,592 |
| **Total** | **39,188** |

`EXECUTORCH_ENABLE_PROGRAM_VERIFICATION` and event tracing were already disabled;
operator and primitive selection were already enabled. Those settings do not address
unused ordinary runtime functions trapped in a retained `.text` section. The current
performance-oriented `-O3` choice also differs from a minimal-size runtime configuration.

## Attribution correction for the size build

GCC emitted function-qualified string pools such as
`.rodata._ZN10executorch7runtime13get_dim_orderERKNS0_7etensor6TensorEPhj.str1.1` with
ELF flags `AMS` (allocated, mergeable, strings). GNU ld attributed a merged 14,051-byte
pool to that first core object. The previous report recognized only `.rodata.str*`,
so it initially misclassified this experimental pool as core data.

The shared string classifier now recognizes both naming forms, with regression coverage
for ET and TFLM and ordinary non-string data. All eight published ET/TFLM images were
checked: their categorization and byte totals are unchanged. The size-build table above
uses the corrected shared-string attribution, consistently with the existing exclusions.

## Records and validation

Artifacts, compile commands, linker maps, symbols, full contribution reports, baseline
hash checks, and the reproduction script are in
`build-artifacts/et-core-size-audit-2026-09-17/`. Exact results are preserved in
[JSON](results/e8-et-core-flash-audit-2026-09-17.json) and
[CSV](results/e8-et-core-flash-audit-2026-09-17.csv).

Both changed runtime variants passed the actual runner's M55 simulator integration:
111 benchmark calls, three exact saved-output checks, zero inference heap growth,
zero extra input allocation, and unchanged 59,744-byte accounted RAM for ResNet8.
These checks validate runtime integration; simulator timings are not used as E8 data.
All 14 Tiny parser/attribution tests pass, and PyLint 3.3.8 reports 10.00/10 for the
changed attribution code and regression test.

These are isolated link-size results. They do not replace the published hardware
measurements, establish changed-binary E8 latency, or measure TFLM's possible savings.
The original toolchain configuration is unchanged pending a coordinated firmware update.
