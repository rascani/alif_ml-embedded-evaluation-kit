<!--
SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates <open-source-office@arm.com>
SPDX-License-Identifier: Apache-2.0
-->

# DS-CNN persistent metadata audit — ExecuTorch v6

The cleaned, trained DS-CNN PTE still uses 8,008 bytes of persistent method metadata,
compared with TFLM's 6,884-byte persistent arena tail. Both frameworks use 20,464 bytes
for planned/head storage. This audit reconstructs all 8,008 bytes from the serialized
`forward` plan, allocator call order, and Cortex-M55 GCC type sizes/alignment. It
matches the board's reported method usage exactly; it is not an instrumented allocation trace.

## Persistent allocation breakdown

| Allocation | Count or calculation | Payload bytes |
| --- | --- | ---: |
| EValue table | 214 values × 16 bytes | 3,424 |
| TensorImpl objects | 62 tensors × 32 bytes | 1,984 |
| Tensor strides | 127 dimensions × 4 bytes | 508 |
| Integer-list value pointers | 64 entries × 4 bytes | 256 |
| Integer-list unboxed buffers | 64 entries × 8 bytes | 512 |
| Integer-list boxed objects | 32 lists × 12 bytes | 384 |
| Instruction argument pointers | 172 arguments × 4 bytes | 688 |
| Instruction argument spans | 12 instructions × 8 bytes | 96 |
| Resolved kernel pointers | 12 instructions × 4 bytes | 48 |
| Chain record | One chain | 16 |
| Input-set flag | One input | 1 |
| Alignment padding | All allocations | 91 |
| **Total persistent method metadata** | | **8,008** |

The value table contains 62 tensors, 118 integers, 32 integer lists, one boolean and
one null. Every value is referenced. All tensors have static shapes: sizes and dimension
order can reference the PTE directly, but the current runtime still allocates their
TensorImpl objects and strides. Integer lists retain their value pointers, unboxed
int64 buffers and boxed-list objects for execution. These are method allocations.

Operator resolution separately uses temporary TensorMeta/dimension-order scratch.
The board records a 212-byte initialization temporary peak and a zero-byte inference
temporary peak. This temporary scratch is excluded from the 8,008-byte persistent total.

## Candidate export optimization

The 118 integer slots contain only 19 distinct integers. For example, `1` appears in
48 slots, `-128` in 21 slots, `0` in 11 slots and `127` in 10 slots. The 32 integer
lists have seven distinct contents: `[1, 1]` appears 21 times, `[0, 0]` five times,
and `[25, 5]` twice.

Deduplicating immutable scalar/list constants in the export is therefore worth
investigating. The 99 duplicate integer slots alone occupy 1,584 bytes of EValue
entries. This is a count of repeated storage, not a demonstrated saving: a rewrite
must preserve value/list aliasing semantics, update references and pass output
validation. All values are referenced, so ordinary unused-operator selection does
not remove them. No PTE or runtime source was changed for this audit.

TFLM's persistent tail uses a different representation and also includes kernel
buffers. The earlier source/model audit identifies 4,608 bytes of raw per-channel
convolution multiplier/shift arrays for this DS-CNN. ET stores corresponding parameter
payloads in the model, while its general value/list representation creates persistent
runtime metadata. Thus a smaller model or operator binary does not imply a smaller
loaded method.

## Evidence and reproduction

The audited PTE is `build-e8-et-tiny-artifacts-v6/kws/ds_cnn.pte`, SHA256
`333c377efb3722f72c50f3afa2c680b87bb43669afc3302d6402c4ad06b99825`.
Runtime source is the frozen ExecuTorch tree `0510beb4b48b8785477a3c11b23c5bc18bd7841a`.

The retained local work is in `build-artifacts/ds-cnn-metadata-audit/`: deserialized
`forward.json`, `value-types.json`, target-compiled `type_sizes.cpp`/`type_sizes.s`,
and `reconcile.py`. The type probe uses the actual method.cpp compilation flags;
the allocation reconstruction follows `Method::parse_values()`, `Method::init()`,
`gen_instruction_arguments()` and `tensor_parser_portable.cpp`. It starts after
the 20,464-byte planned allocation and reaches the board's 28,472-byte method cursor.

[Exact allocation reconstruction](results/e8-ds-cnn-metadata-audit-2026-09-17.json) ·
[Board RAM comparison](e8_tiny_board_results_2026_09_17.md#accounted-inference-ram)
