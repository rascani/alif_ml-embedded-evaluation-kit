<!--
SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates <open-source-office@arm.com>
SPDX-License-Identifier: Apache-2.0
-->

# E8 persistent arena and method allocations — 18 September 2026

ResNet8 uses 5,300 bytes of persistent TFLM arena storage and 5,640 bytes of
ExecuTorch method metadata. The 340-byte difference combines substantially larger ET
tensor/value metadata with savings from keeping prepared kernel constants in the PTE.
These are the latest TFLM v3 and integer-pooled ET v8 SRAM builds.

This comparison excludes planned tensor/scratch buffers, outside persistent objects and
heap allocations, global registries, transient initialization allocations, and stack.
In particular, this is not the full 648-byte ResNet8 accounted-inference-RAM difference.
Both runtimes use 49,728 bytes for ResNet8 planned/head buffers.

## Persistent storage across all four models

Bytes. TFLM totals are the arena tail after removing the existing 32-byte allocation
audit overhead. ET totals are method-pool usage minus planned buffers.

| Model | TFLM persistent arena | ET method metadata | ET minus TFLM |
| --- | ---: | ---: | ---: |
| DS-CNN | 6,884 | 5,056 | -1,828 |
| ResNet8 | 5,300 | 5,640 | +340 |
| MobileNetV1 0.25 | 27,044 | 12,372 | -14,672 |
| Deep autoencoder | 8,500 | 3,552 | -4,948 |

All eight totals match the existing E8 board records exactly. No benchmark firmware
or model was modified for this investigation, and these are not new latency results.

## ResNet8 comparison by purpose

Payload bytes, with alignment separated into the final row. The groupings describe
similar purposes; the underlying data structures are not identical.

| Purpose | TFLM | ExecuTorch | ET minus TFLM |
| --- | ---: | ---: | ---: |
| Tensor/value records and I/O metadata | 568 | 4,316 | +3,748 |
| Graph execution records | 548 | 1,048 | +500 |
| Operator options, kernel state and integer-list storage | 3,963 | 252 | -3,711 |
| Arena allocator/planner objects | 124 | 0 | -124 |
| Alignment and input-set flags | 97 | 24 | -73 |
| **Total** | **5,300** | **5,640** | **+340** |

ET scalar operator arguments reside in EValue slots, so they are included in the first
row; its integer-list allocations are in the third. ET allocator-management objects
are allocated outside the method pool and excluded from this comparison, rather than
being free. TFLM's input/output tensor descriptors and their quantization metadata are
included in its first row. Global operator registries/resolvers are excluded for both.

### TFLM exact breakdown

| Allocation | Calculation or meaning | Payload bytes |
| --- | --- | ---: |
| Eval tensor descriptors | 38 × 12 | 456 |
| Full input/output tensor descriptors | 2 × 32 | 64 |
| I/O quantization structs and zero-point arrays | 2 × (12 + 8) | 40 |
| I/O tensor pointer arrays | 2 × 4 | 8 |
| Node and registration records | 16 operators × 32 | 512 |
| Subgraph record | One subgraph | 8 |
| Scratch-buffer handles | Seven pointers | 28 |
| Parsed operator options | Conv, add, pool, reshape, FC and softmax options | 343 |
| Kernel OpData | State allocated by 15 operator init callbacks | 892 |
| Convolution output multipliers | 336 output channels × 4 | 1,344 |
| Convolution output shifts | 336 output channels × 4 | 1,344 |
| Fully-connected kernel sums | Ten output channels × 4 | 40 |
| Single-arena allocator | Excludes allocation-audit fields | 36 |
| Greedy memory planner | Planner object retained after preparation | 44 |
| MicroAllocator | Runtime allocator object | 36 |
| Builtin-data allocator | Operator option allocator object | 8 |
| Alignment padding | Measured allocation consumption minus payload | 97 |
| **Total** | | **5,300** |

The nine convolution layers have 16, 16, 16, 32, 32, 32, 64, 64 and 64 output
channels. CMSIS-NN preparation allocates one int32 multiplier and shift per channel.
The fully-connected preparation path with `KERNELS_OPTIMIZED_FOR_SPEED` also stores
precomputed kernel sums persistently. These 2,728 bytes account for 51.5% of the tail.

The 892-byte OpData payload comprises nine 60-byte conv records, three 60-byte add
records, a 36-byte pool record, a 72-byte fully-connected record and a 64-byte softmax
record. Reshape has parsed options but no persistent init allocation in this trace.

### ExecuTorch exact breakdown

| Allocation | Calculation or meaning | Payload bytes |
| --- | --- | ---: |
| EValue slots | 105 × 16 | 1,680 |
| TensorImpl objects | 65 × 32 | 2,080 |
| Tensor strides | 139 dimensions × 4 | 556 |
| Integer-list value pointers | 14 × 4 | 56 |
| Integer-list unboxed values | 14 × 8 | 112 |
| Integer-list objects | Seven × 12 | 84 |
| Chain record | One chain | 16 |
| Resolved kernel pointers | 15 instructions × 4 | 60 |
| Instruction argument spans | 15 × 8 | 120 |
| Instruction argument pointers | 213 × 4 | 852 |
| Input-set flag | One input | 1 |
| Alignment padding | Allocation-order reconstruction | 23 |
| **Total** | | **5,640** |

The 105 EValues are 65 tensors, 31 integers, seven integer lists, one boolean and
one null. TensorImpl objects and strides cost 2,636 bytes in addition to the EValue
slots. Their combined 4,316 bytes account for 76.5% of method metadata.

The Cortex-M operators consume quantization arrays and kernel sums stored in the PTE.
Their payloads do not need TFLM-style persistent preparation allocations, but ET still
needs runtime descriptors for its tensor arguments, including constant tensors. It also
builds instruction argument-pointer tables. Integer pooling already saved 3,280 bytes
on ResNet8; the remaining method storage is dominated by tensor/value representation.

## Why the other models favor ET

TFLM's persistent prepared kernel constants grow with channel counts. These are raw
payloads; OpData, graph/tensor records and alignment are additional.

| Model | Conv/depthwise multiplier and shift arrays | FC kernel sums | Total prepared constants in TFLM RAM |
| --- | ---: | ---: | ---: |
| DS-CNN | 4,608 | 48 | 4,656 |
| ResNet8 | 2,688 | 40 | 2,728 |
| MobileNetV1 0.25 | 21,888 | 8 | 21,896 |
| Deep autoencoder | 0 | 6,688 | 6,688 |

These allocations explain much of ET's persistent-storage advantage on MobileNetV1
and the autoencoder. ResNet8 saves fewer prepared-constant bytes, leaving a small net
increase after ET's larger execution representation is included.

## Evidence and reproduction

TFLM was traced on the Corstone-300 Cortex-M55 simulator using the existing GCC 15.2.1
E8 `-Oz` runtime and `-O3` CMSIS-NN libraries, the frozen TFLM v3 models and their
INT8 resolver headers. Only a diagnostic copy of `TflmMemoryAudit.cc` was instrumented:
each persistent allocation reports its request, alignment, actual arena consumption and
caller address. Caller addresses were symbolized against the diagnostic ELF, including
inline frames. This does not change runtime object sizes or arena allocation order.

The probe runs initialization and one zero-input inference per model. Each output hash
matches sample zero from the previous specialized-versus-generic M55 validation. All
four planned/head sizes and persistent totals match E8, and all report zero inference
allocation calls. Simulator timing and heap effects from trace printing are not used.

ET uses the existing target-ABI/source reconstruction from the integer-pooling audit,
whose total was validated against the E8 method allocator counters. It is not a new
instrumented ET allocation trace. Different model formats and lowered graphs mean the
two sides do not have identical tensor or instruction counts.

The [machine-readable audit](results/e8-tiny-persistent-allocation-audit-2026-09-18.json)
contains every TFLM allocation with symbolized caller, removed audit overhead, categorized
payloads and padding, all ET reconstruction fields, model/library/probe hashes, and board
total/output checks. Local diagnostic sources, ELF files, commands and logs are retained in
`build-artifacts/tiny-persistent-audit/`.

With the current local build libraries and toolchain, reproduce using:

```sh
python3 build-artifacts/tiny-persistent-audit/run_probe.py
python3 build-artifacts/tiny-persistent-audit/reconcile.py
```

The linker and compilation commands are also recorded beside each diagnostic output.
The reproduction scripts reference the existing frozen bundles/build directories; they
are local audit artifacts rather than a standalone firmware package.

## Backend registry clarification

A global is eligible for linker garbage collection when no retained code references it.
The current ET method loader includes delegate-loading support, which calls
`get_backend_class()` and retains the backend registry. An empty delegate list in this
particular PTE is known only at runtime. Removing the registry requires eliminating or
stubbing the delegate lookup path for a build that intentionally rejects delegates.
Its 132 bytes are outside the method pool and excluded from the comparison above.
No backend-registry change was made as part of this audit.

[Current board comparison](e8_tiny_current_summary.md) ·
[Integer-pooling results](e8_et_tiny_v8_results.md)
