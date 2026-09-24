<!--
SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates <open-source-office@arm.com>
SPDX-License-Identifier: Apache-2.0
-->

# E8 Tiny measurement definitions

These are CPU-only runtime/model measurements using MLPerf Tiny networks. They are
not an official MLPerf submission or a shared dataset accuracy evaluation. The final
ET and TFLM models derive from trained reference weights, but quantization/calibration
and potentially preprocessing contracts differ. ET's saved-output checks establish
agreement with its supplied reference examples, not equivalent end-to-end accuracy.

## Latency and cycles

Each boot runs one separately timed first inference, ten additional warmups, and
100 measured calls. The current collection uses three complete boots per model and
framework, pooling 300 measured calls. First calls and warmups are excluded from
steady-state statistics. P95 uses the nearest-rank convention. Convert cycles to
seconds using the reported core frequency; the E8 reports 400,000,000 Hz.

The timed boundary is the model wrapper's `RunInference()` call. Deterministic
`synthetic_v1` inputs are filled before each call. Sample storage is allocated before
timing; UART formatting, result aggregation and saved-output validation happen after
the measured batch. Caches are not flushed, so steady-state results include reuse
across calls and input preparation can affect cache state. The first inference occurs
after initialization; it is not a controlled cold-cache measurement or load/init timing.

Both frameworks use the Alif HAL's SysTick-derived `CPU TOTAL` counter. The
[independent DWT check](e8_timer_validation.md) validates rollover and cycle accounting.
Both counters share the CPU clock, so their agreement does not calibrate its frequency.

The paired compiler profiles use `-Oz` for runtime/operator wrappers and `-O3` for
CMSIS-NN/CMSIS-DSP, function/data sections and linker garbage collection, without LTO.
Logging is enabled for latency/RAM collection. Separate logging-disabled builds
measure flash; no silent-build latency or RAM measurement is claimed. Compiler audits
check the effective final optimization flags, logging definitions and CMSIS builtins.

## Flash attribution

All sizes are bytes; divide by 1,024 for KiB. GNU linker-map input sections and ELF
sections identify bytes retained after garbage collection and linker relaxation.

| Component | Included |
| --- | --- |
| Model | Exact serialized PTE or TFLite graph, weights and constants |
| Operators | Framework kernels/utilities, CMSIS-NN and selected resolver/registry code |
| Core | Runtime execution, allocation and planning |
| Filtered flash | Model + operators + core |
| Full MRAM payload | Application image, including runner, platform and other support |

Filtered flash excludes the runner, diagnostics, saved validation fixtures, platform
startup/PAL, MLEK adapters, shared C/C++ libraries, merged string pools and linker
tables/padding. It is not a deployable firmware total. Full MRAM includes initialized
data copied to RAM, but excludes BSS, reserved arenas, SE Tools device configuration,
boot-package metadata and final programming padding.

The scripts retain contribution-level evidence and reject unclassified ownership or
inconsistent totals. Merged strings and COMDAT ownership cannot always be uniquely
assigned to a framework; excluded shared support must remain visible as a separate
cost. The parsers are specific to the GNU/Alif section and archive conventions.

## Accounted inference RAM

Reservations describe available capacity. Usage and peaks describe consumed storage.
Our comparison reports accounted inference memory, not whole-device peak RAM or the
smallest arena capacity with which a model could initialize.

| Framework | Disjoint terms in the reported total |
| --- | --- |
| TFLM | Inference arena peak + outside persistent model/resolver and initialization heap allocations |
| ExecuTorch | Method pool used + inference temporary-pool peak + outside persistent model/initialization allocations + ELF-attributed runtime/registry static storage |

TFLM's arena contains both activation/scratch head and persistent runtime/kernel tail.
Do not add its persistent tail again to the arena peak. Its heap-allocated interpreter
is already included in the initialization heap delta. The audit allocator's additional
tracking storage is subtracted once while preserving ordinary allocation alignment.
Initialization peaks are recorded separately: the greedy planner can temporarily use
almost all reserved capacity, which is not a minimum-arena requirement.

ET's planned tensors/scratch are already inside the method pool. The remaining method
usage covers execution metadata, alignment and any unplanned input storage. Planned
inputs have no separate staging allocation. The temporary allocator's inference peak
is reset after initialization and sampled before output validation; initialization
temporary peaks are reported separately. The final four models use zero inference
temporary bytes, which does not imply they need no initialization workspace.

Outside persistent storage includes the wrapper object and retained libc heap delta
across model initialization. Heap snapshots use `mallinfo`/`mallinfo2` and include
allocator bookkeeping. The inference batch must not retain extra heap allocations;
diagnostic formatting allocations are measured separately. ET's runtime static storage
is attributed from linked writable sections and added once by the host parser.

Excluded from the comparison are unused pool reservations, call-stack high water,
transient heap peaks, initialization workspace and benchmark/platform/reporting memory.
Comparing metadata categories alone also needs care: one runtime may serialize
constants in the model that the other computes and retains in RAM.

## Reproducibility and collection

Keep each bundle's manifest, firmware/model hashes, source revisions or patched-tree
identity, compiler audit, linker map and selection metadata with its raw UART logs.
Parsers verify model/build identity, all samples, recomputed summaries, memory totals
and required output checks. Preserve incomplete attempts separately; choose a complete
collection explicitly. New binaries require new measurements.

Use the final comparison CSV/JSON in the repository for the frozen aggregate values.
Historical firmware commit IDs remain recorded even after branch-history cleanup;
they identify the originally measured sources. Detailed historical reports and
per-boot evidence are retained in the separate documentation archive. Fresh packages
carry their own manifests and capture output rather than copied historical results.
