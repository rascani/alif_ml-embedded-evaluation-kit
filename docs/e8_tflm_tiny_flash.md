<!--
SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates <open-source-office@arm.com>
SPDX-License-Identifier: Apache-2.0
-->

# TFLM Tiny flash attribution

The measured E8 images contain substantial benchmark and platform support. For framework
comparisons, use the directly attributed **model + TFLM/CMSIS-NN + selected resolver**
footprint below. This filters out runner/profiler/memory-audit objects, platform/startup,
dedicated framework logging objects, and separately reports the MLEK adapter and shared
C/C++ toolchain support. The original binaries and board measurements are unchanged.

These are component costs in the existing logging-enabled image, not a standalone
deployable image size. Runtime/kernel/resolver objects still include their inline logging
call sites and non-merged strings. Merged string pools are shared support; a fully
logging-free footprint requires a separate size build.
Shared libc/libstdc++/libgcc support serves both inference and application code; some of it
will still be required by a deployed runtime. It is not assigned entirely to either side.

## Filtered numbers

| Model | Model bytes | Attributed runtime bytes | Model + runtime bytes | Model + runtime KiB |
| --- | ---: | ---: | ---: | ---: |
| KWS | 53,936 | 94,912 | 148,848 | 145.36 |
| Image classification | 98,496 | 94,572 | 193,068 | 188.54 |
| Visual wake words | 333,288 | 94,912 | 428,200 | 418.16 |
| Anomaly detection | 276,976 | 31,440 | 308,416 | 301.19 |

The runtime subtotal consists of these retained code/data contributions, in bytes:

| Component | KWS | IC | VWW | AD |
| --- | ---: | ---: | ---: | ---: |
| TFLM core runtime | 18,032 | 17,968 | 18,032 | 16,652 |
| TFLM operator implementations and utilities | 18,508 | 31,692 | 18,508 | 4,292 |
| CMSIS-NN | 56,776 | 43,312 | 56,776 | 10,224 |
| Selected operator resolver | 1,596 | 1,600 | 1,596 | 272 |
| **Runtime subtotal** | **94,912** | **94,572** | **94,912** | **31,440** |

The TFLM core contains the interpreter, allocator, memory planners, contexts and schema
support. The operator row contains TFLM's kernels, CMSIS-NN wrappers, reference paths and
shared kernel utilities. These two rows partition the earlier combined TFLM library row;
all runtime subtotals are unchanged. Source paths from Bloaty's compile-unit reports
classify each retained TFLM archive member, while the linker map still supplies its bytes.
All retained members have an unambiguous core/operator category in these images.

The [detailed CSV](results/e8-tflm-tiny-runtime-detail-2026-09-16.csv) and
[object contributions and source mappings](results/e8-tflm-tiny-runtime-detail-2026-09-16.json)
record this subdivision. The largest core contributors include `micro_allocator` (3,988 B),
`micro_allocation_info` (2,516 B), `greedy_memory_planner` (2,196 B), `micro_interpreter_graph`
(2,180 B), and `micro_interpreter` (2,056 B), with the same costs in all four images.

KWS and VWW have identical runtime costs because they select the same six operator types.
Operator selection retains the currently linked numeric variants; these figures do not
claim an INT8-only kernel build. IC's TFLM `add.cc` object alone contributes 17,012 bytes.
KWS/VWW retain the 3,828-byte CMSIS-NN `arm_depthwise_conv_s4` object despite their INT8
inputs; per-operator numeric specialization remains a separate footprint optimization.

## Reconciliation to the programmed image

Every byte in the original payload is accounted for below. All values are bytes.

| Component | KWS | IC | VWW | AD |
| --- | ---: | ---: | ---: | ---: |
| Filtered model + runtime | 148,848 | 193,068 | 428,200 | 308,416 |
| MLEK framework adapter | 6,568 | 6,568 | 6,568 | 6,568 |
| Dedicated TFLM logging objects | 244 | 244 | 244 | 244 |
| Runner, profiling, memory diagnostics | 17,020 | 17,020 | 17,020 | 17,016 |
| Shared merged strings | 19,859 | 19,659 | 19,859 | 16,299 |
| Platform and startup | 79,467 | 79,467 | 79,467 | 79,467 |
| Shared C/C++ toolchain support | 89,139 | 89,139 | 89,139 | 88,331 |
| Linker tables, alignment, unowned bytes | 235 | 231 | 235 | 207 |
| **Complete MRAM payload** | **361,380** | **405,396** | **640,732** | **516,548** |

The adapter bucket includes `TflmModel`, `TflmTensor`, and its logging bridge. Shared
toolchain support includes memory/math helpers, allocation, formatting, termination and
demangling. Excluding these buckets from the direct ML subtotal does not imply that all
their bytes can be removed from a working application.

## Method and reproduction

The analysis uses the retained input sections in each GNU linker map. It includes only
ELF output sections stored in MRAM, including initial data copied into DTCM. BSS, arena,
heap and stack reservations, discarded sections, ELF metadata and debug data are excluded.
Input section sizes are taken after linker relaxation. Symbol aliases are not summed.
The script checks for overlapping/out-of-bounds contributions and reconciles section
totals plus alignment to the exact `mram.bin` length.

`libtflu.a` and `libcmsis-nn.a` contributions form the core runtime/kernel costs. Dedicated
`debug_log`, `micro_log`, `micro_error_reporter` and `error_reporter` objects are separate.
The resolver's separately emitted methods/vtable and generated `EnlistOperations` and
`GetOpResolver` methods are retained in the runtime total even though they are compiled
in `MainLoop.cc.obj`. The remaining application objects are excluded.

GNU ld attributes a merged string pool to its first input object, even when most strings
come from other objects. All `.rodata.str*` sections are therefore shared support. This
correction moves bytes out of the runner bucket in these TFLM images; the reported TFLM
runtime/model subtotals are unchanged. COMDAT helpers remain attributed to the selected
object, without establishing exclusive use. Linker maps capture more read-only-data
ownership than Bloaty's compile-unit view, whose unassigned bytes also include model data
and toolchain support. Bloaty independently confirms the stored-section totals for all
four images. Four bytes of alignment between stored sections complete each image.

Run from the repository root:

```bash
resources_downloaded/env/bin/python scripts/py/tflm_tiny_flash.py \
  --bundle build-e8-tflm-tiny-artifacts \
  --output-dir build-artifacts/tflm-tiny-flash
```

The script verifies the original bundle checksums before analyzing it. It writes
`summary.csv`, `summary.json`, and a per-model contribution list with section, address,
size, object and category. Bloaty compile-unit reports are also preserved in that output
directory. No rebuilding or reflashing is needed for this attribution.

[Saved CSV](results/e8-tflm-tiny-flash-2026-09-16.csv) and
[definitions, byte totals and ELF/map hashes](results/e8-tflm-tiny-flash-2026-09-16.json)
record this analysis. The [board summary](results/e8-tflm-tiny-2026-09-16.csv) now has
`flash_filtered_runtime_bytes` and `flash_filtered_model_runtime_bytes` columns alongside
the original full-image costs. Latency and RAM fields are unchanged.
