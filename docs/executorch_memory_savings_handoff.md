<!--
SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates <open-source-office@arm.com>
SPDX-License-Identifier: Apache-2.0
-->

# Handoff prompt: investigate ExecuTorch execution-metadata RAM savings

Investigate opportunities to reduce ExecuTorch's persistent execution metadata for
four MLPerf Tiny models running CPU-only on an Alif E8 Cortex-M55-HP. Where useful,
prototype candidates independently in an isolated checkout and report measured savings
and tradeoffs. Start with ResNet8, then check applicability to all four models.

The current benchmark comparison is frozen. We deliberately stopped optimizing it.
This is a separate exploration: preserve the existing ET/TFLM source state, firmware,
models, build directories, returned board logs and published comparison numbers. Do not
merge, push, replace benchmark bundles, or require a new board collection as part of
the initial investigation. Do not change inference-pool placement or model accuracy
to obtain savings.

## Workspace and evidence

MLEK repository:

`/home/rja/alif_ml-embedded-evaluation-kit`

Read its `AGENTS.md`. Its fork branch is `feat/e8-cpu-inference-runner`. Work in a
separate branch/checkout and new build/output directories. There may be uncommitted
analysis documents and staged changes in the ET tree; preserve them. Copy necessary
untracked evidence into your workspace explicitly, since a Git worktree will not
automatically contain it.

The ET source used by the benchmark is:

`/home/rja/alif_ml-embedded-evaluation-kit/resources_downloaded/et_tiny/executorch`

Do not assume `dependencies/executorch` is the benchmark runtime. The frozen source
identity is Git **tree** `0510beb4b48b8785477a3c11b23c5bc18bd7841a`, recorded as
`executorch_tree` in the bundle manifest. This is a tree object, not a commit ID.
The build incorporates staged source patches, so `HEAD` alone is not the baseline.
Verify the tree and local state before copying it into an isolated experiment; do not
reset, clean, stage or commit somebody else's working tree. If evaluating newer ET
code, first reproduce the pinned baseline and report the version change separately.

Read these files relative to the MLEK root:

- `docs/e8_tiny_persistent_allocations.md`: detailed TFLM/ET allocation comparison.
- `docs/results/e8-tiny-persistent-allocation-audit-2026-09-18.json`: every traced
  TFLM persistent allocation, source attribution, ET reconstruction, and provenance.
- `docs/e8_et_tiny_v8_integer_pooling.md`: frozen ET configuration and build guide.
- `docs/e8_et_tiny_v8_results.md`: measured ET v8 board results.
- `docs/results/e8-tiny-board-2026-09-17-sram-v8-v3.json`: exact latest board comparison.
- `build-e8-et-tiny-artifacts-v8-sram-integer-pooling/manifest.json`.
- `build-e8-et-tiny-artifacts-v8-sram-integer-pooling/validation/pte-comparison.json`:
  ET value counts and allocation reconstruction for each model.
- `build-e8-et-tiny-artifacts-v8-sram-integer-pooling/validation/fvp/`: existing M55
  simulator validation and link commands.
- `build-artifacts/tiny-persistent-audit/`: local TFLM diagnostic sources, reproduction
  scripts, ELF files, allocation traces and output checks.

The ET bundle's model directories are `kws` (DS-CNN), `ic` (ResNet8), `vww`
(MobileNetV1 0.25), and `ad` (deep autoencoder). Each contains its frozen PTE, ELF,
map, symbols and memory attribution. The bundle also retains its export and validation
fixtures. Its `size/` directory contains separate logging-disabled builds. TFLM's
baseline bundle is `build-e8-tflm-tiny-artifacts-v3`.

## Baseline and accounting

- Cortex-M55-HP, 400 MHz, CPU-only; no NPU/delegates.
- GCC 15.2.1, `-Oz` runtime/operator wrappers, CMSIS-NN 8.0.0 at `-O3`.
- Function/data sections and linker garbage collection enabled; no LTO.
- Logging enabled for latency/RAM observations; separate silent builds for flash.
- Model-specific operators and primitive selection enabled; no primitives selected.
- Models have static shapes and int8 inputs/outputs. Verify these properties rather
  than assuming they generalize to arbitrary programs.
- Method/planned pool: SRAM at `0x02000000`, reserved 256 KiB.
- Temporary pool: SRAM at `0x02040000`, reserved 64 KiB.
- Code and PTEs: MRAM. Ordinary globals, heap and stack: DTCM.
- Keep inference pools in SRAM. Do not reintroduce the removed DTCM-pool experiment.
- Redundant input buffers have already been removed. Integer and integer-list
  deduplication is already present in these PTEs. Do not count those savings again.

Measured persistent arena/method storage, in bytes:

| Model | TFLM persistent arena tail | ET method metadata |
| --- | ---: | ---: |
| DS-CNN | 6,884 | 5,056 |
| ResNet8 | 5,300 | 5,640 |
| MobileNetV1 0.25 | 27,044 | 12,372 |
| Deep autoencoder | 8,500 | 3,552 |

These figures exclude planned tensors/scratch, outside-pool objects/heap, global
registries, transient initialization memory and stack. ET method metadata means
method-pool usage minus planned buffers. TFLM allocator/planner objects are inside its
tail; ET's allocator-management objects are outside its method pool. Avoid treating
those differently located allocations as eliminated overhead.

For ResNet8, both planned/head buffers use 49,728 bytes. Full accounted inference RAM
is TFLM 55,816 versus ET 56,464 bytes. The 648-byte difference comprises 340 bytes of
persistent arena/method storage, 20 bytes of outside persistent state, and 288 bytes
of separately attributed ET runtime static storage. ET's inference temporary peak
and separate input allocation are both zero.

ResNet8 ET metadata breakdown:

| Allocation | Bytes |
| --- | ---: |
| 105 EValues × 16 | 1,680 |
| 65 TensorImpl objects × 32 | 2,080 |
| Strides: 139 dimensions × 4 | 556 |
| Integer-list EValue pointers | 56 |
| Integer-list unboxed int64 buffers | 112 |
| Seven boxed integer-list objects | 84 |
| Chain record | 16 |
| Resolved kernel pointers | 60 |
| Instruction argument spans | 120 |
| 213 instruction argument pointers × 4 | 852 |
| Input-set flag | 1 |
| Alignment | 23 |
| **Total** | **5,640** |

There are 65 tensor values, 31 integers, seven integer lists, one boolean and one
null. Integer pooling already saved 3,280 metadata bytes on this model. TFLM has
smaller tensor/execution records but retains prepared kernel constants in RAM:
ResNet8 uses 2,688 bytes of convolution multipliers/shifts plus 40 bytes of FC kernel
sums. ET reads corresponding constants from the PTE. Preserve this distinction when
comparing representations and accounting for flash-versus-RAM changes.

## Candidates to investigate

The figures below identify current storage or conditional savings, not demonstrated
reductions. Account for padding, bookkeeping, interactions and any displaced storage.

### 1. Share immutable stride arrays

`runtime/executor/tensor_parser_portable.cpp` points static tensor sizes and dimension
order into the PTE, but allocates and computes a separate stride array for every tensor.
ResNet8 spends 556 bytes on these arrays.

Count distinct stride vectors and derive exact per-model savings from interning them
at load time. Include any retained lookup-table cost; prefer initialization-only lookup
workspace where practical. Confirm that static-shape kernels cannot mutate shared
strides, and retain independent writable storage for dynamic tensors. Check all relevant
resize and metadata-access paths rather than relying only on shape annotations.

As a separate, more invasive option, assess serializing immutable strides into the PTE
and referencing them in place. Explain schema/export compatibility, alignment, flash
growth and MRAM-access implications. The full 556 bytes is a storage ceiling for this
candidate, not the expected saving from sharing alone. Do not remove stride APIs while
existing kernels still depend on them.

### 2. Smaller static-shape tensor descriptors

Inspect `runtime/core/portable_type/tensor_impl.h` and `.cpp`. Each ResNet8 TensorImpl
is 32 bytes on the actual M55 ABI; every four bytes removed saves 260 bytes over 65
tensors, before any secondary effects.

One candidate is the separate `numel_bound_` field used for dynamic resizing. Determine
whether a static-shape build or representation can eliminate it while retaining shape
validation. Look for other genuinely redundant state, but do not assume reordering
already compact fields will produce savings.

Quantify ABI impact and ensure runtime, generated wrappers, extensions and kernels all
use the same layout. Preserve the general dynamic-shape path unless an explicit static
configuration rejects unsupported programs clearly. Do not use unsafe packed structs,
truncate element counts, or move the cost to stack/heap without reporting it.

### 3. Immutable integer-list representation

`Method::parse_values()` currently builds EValue-pointer arrays, unboxed int64 arrays,
and `BoxedEvalueList<int64_t>` objects. That totals 252 bytes for ResNet8's seven lists,
in addition to the associated EValue slots.

Determine which lists and referenced scalars are provably immutable. Investigate a
direct immutable-list representation that avoids redundant pointers and repeated
materialization. Keep generic mutable lists correct: MoveCall/control flow or mutation
of referenced EValues can invalidate an assumption based solely on the initial values.
If changing serialization, include PTE/schema compatibility and flash cost. Explain
which EValue slots would remain and whether any newly unreferenced values could be
removed; do not assume all integer slots become unnecessary.

### 4. Reuse instruction-argument workspace

`gen_instruction_arguments()` in `runtime/executor/method.cpp` allocates persistent
EValue-pointer arrays per instruction. ResNet8 uses 852 bytes for those arrays plus
120 bytes for argument spans; serialized argument indices already exist in the PTE.

Explore a reusable buffer sized to the largest call, reconstructed before each dispatch,
or another representation that avoids retaining all expanded argument pointers. Derive
the actual maximum argument count for each model. Account for buffer lifetime,
reentrancy, nested methods/control flow and pointer retention by kernels. Retain input
validation and correct behavior for unsupported cases.

This explicitly trades precomputed dispatch state for inference work. Report added
index decoding, MRAM reads and pointer setup. Moving storage into a temporary allocator
or stack is not a net saving unless peak accounting includes it. Do not claim a latency
improvement based on a simulator; flag this candidate for a future E8 re-benchmark.

### 5. Remove delegate support and its empty backend registry

Ethos-U is already disabled: `ETHOS_U_NPU_ENABLED=OFF`,
`EXECUTORCH_BUILD_ARM_BAREMETAL=OFF`, and `EXECUTORCH_BUILD_ARM_ETHOSU_LINUX=OFF`.
No Ethos-U backend registration is linked. The generic loader retains delegate lookup
support, which references the empty global backend registry.

`runtime/backend/interface.cpp` reserves 16 backend entries (128 bytes on M55) plus a
four-byte count. Investigate an explicit configuration without delegate support that
rejects delegate-bearing programs and lets the lookup/registry code disappear. Confirm
the 132-byte static RAM reduction from the linked map and quantify associated flash
changes. This is outside method metadata; report it separately. A global variable is
not inherently immune to linker garbage collection—remaining references matter.

### Optional longer-term item: compact EValues

The current EValue is 16 bytes because its payload supports int64/double with eight-byte
alignment, followed by a tag. Narrowing the tag alone will not shrink the object. Assess
only if a credible representation change preserves integer/double semantics, alignment,
tag handling and ABI compatibility. Treat this as a larger redesign, not an easy packing
optimization. Avoid expanding the project indefinitely if the earlier candidates give
a clearer cost/benefit result.

## Validation and measurement

1. Reproduce baseline type sizes and allocator totals using the frozen model/runtime
   identities. Native x86 sizeof results are not the Cortex-M55 ABI.
2. Make candidates independently selectable in your experiment. Measure each against
   the same baseline before combining successful candidates.
3. Use the existing Corstone-300 M55 harness and E8 runtime/kernel libraries where
   appropriate. Starting points are `scripts/py/validate_tiny_fvp.py`,
   `tests/integration/tiny_fvp/`, and the frozen bundle's validation outputs.
   Existing builders pin the source tree and use shared build paths; do not run them
   unmodified against experimental sources or weaken their identity checks globally.
4. Validate outputs against frozen references on all four models. Use available saved
   inputs and meaningful additional cases. Exercise the specific aliasing, lifetime,
   dynamic-shape or malformed-input behavior affected by each implementation.
5. Report persistent method usage, planned storage, initialization/inference temporary
   peaks, outside retained allocations, and attributed static RAM separately. Include
   any new stack or transient heap costs and state limits of high-water measurements.
6. Report PTE size, runtime/operator flash and full firmware changes separately. Match
   optimization settings and logging profiles. Do not equate ELF file size with flash.
7. Distinguish measured savings, source/ABI predictions and upper bounds. Do not add
   overlapping estimates or count moved storage as eliminated storage.
8. The physical E8 is on another host. Keep future board measurements pending; preserve
   current latency claims. Mark candidates that need re-benchmarking and explain why.

## Deliverables

- A concise recommendation ranked by net RAM benefit, complexity, compatibility and
  likely latency impact. Explain rejected approaches as well as promising ones.
- A per-model table for each candidate: baseline/new metadata, static RAM, temporary
  costs, net accounted RAM, PTE bytes, runtime/operator flash, and validation status.
- Exact allocation/symbol evidence and reproducible commands, with source/model/compiler
  identities and machine-readable results alongside the written report.
- Isolated patches or branches for prototypes that were actually implemented, with
  clear separation from estimates. Leave the benchmark baseline untouched.

Prioritize stride sharing and static descriptor size first. Then evaluate immutable
integer lists and argument workspace reuse. Treat delegate-registry removal as a small,
separate static/flash cleanup. Stop at a concrete assessment and validated prototypes;
do not turn this into an open-ended optimization campaign.
