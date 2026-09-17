<!--
SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates <open-source-office@arm.com>
SPDX-License-Identifier: Apache-2.0
-->

# TFLM int8 registration audit — 17 September 2026

The TFLM v2 / ExecuTorch v5 operator-flash comparison is still asymmetric in type
selection. Our generated TFLM resolver selects the operators present in the model
but calls generic registrations such as `AddConv2D()` and `AddFullyConnected()`.
Those registrations retain float32, int4-weight, and int16-activation execution
paths. The selected ET Cortex-M operators use narrower int8 paths.

## Available registrations in the pinned TFLM checkout

Runtime revision: `50b720726a25e39bc381187b0dd39669ac425262`.

| TFLM builtin | Explicit CMSIS-NN registration | Used by |
| --- | --- | --- |
| CONV_2D | `Register_CONV_2D_INT8()` | KWS, IC, VWW |
| DEPTHWISE_CONV_2D | `Register_DEPTHWISE_CONV_2D_INT8()` | KWS, VWW |
| FULLY_CONNECTED | `Register_FULLY_CONNECTED_INT8()` | All four |
| AVERAGE_POOL_2D | `Register_AVERAGE_POOL_2D_INT8()` | KWS, IC, VWW |
| ADD | `Register_ADD_INT8()` | IC |
| SOFTMAX | `Register_SOFTMAX_INT8()` | KWS, IC, VWW |
| RESHAPE | Keep `Register_RESHAPE()` | KWS, IC, VWW |

For example:

```cpp
resolver.AddConv2D(tflite::Register_CONV_2D_INT8());
resolver.AddFullyConnected(tflite::Register_FULLY_CONNECTED_INT8());
resolver.AddSoftmax(tflite::Register_SOFTMAX_INT8());
```

The resolver's `Add*` methods accept a registration argument. Header declarations
select the actual specialized functions when `CMSIS_NN` is defined, as it is in
our E8 compilation commands. On some other backends these names are inline aliases
for the generic registration, so calling the name alone does not prove specialization.
`RESHAPE` handles shape checks and a byte copy (or does nothing in place), rather
than selecting separate numeric kernels.

Inspected every node in all four frozen TFLite models: numerical activations,
outputs and convolution/fully-connected weights are int8. Biases are int32 and
reshape shape tensors are int32, as expected. Model-specific generation should
check those operator-specific signatures across every node/subgraph before selecting
a specialized registration; a blanket rule requiring every tensor to be int8 is wrong.
For other models, mixed signatures must retain a compatible generic registration.

## Evidence from the existing silent size images

These values are retained linker-map bytes in v2, not measured savings from a new
build. Operator totals include wrappers/utilities, CMSIS-NN, and registry/resolver.

| Model | TFLM operators (bytes) | ET operators (bytes) | CMSIS s4-named objects | CMSIS s16-named objects | Extra s8-to-s16 softmax entry + common helper |
| --- | ---: | ---: | ---: | ---: | ---: |
| KWS | 67,864 | 26,150 | 19,332 | 7,208 | 6,784 |
| IC | 57,158 | 18,132 | 12,780 | 6,460 | 6,784 |
| VWW | 67,864 | 24,494 | 19,332 | 7,208 | 6,784 |
| AD | 12,212 | 2,924 | 2,100 | 1,388 | 0 |

The last three columns partition selected CMSIS contributions by object name;
`s8_s16` is kept separate from other `s16` objects. They exclude additional float
reference code and type dispatch inside TFLM wrappers. Some buffer-size query code
can remain reachable from shared preparation functions after int8 registration.
They therefore must not be subtracted as an exact forecast of the resulting binary.

In KWS, the operator gap is 41,714 bytes (40.74 KiB). The columns identifying
s4/s16 and the extra softmax path total 33,324 bytes (32.54 KiB), explaining most
of that gap. `arm_softmax_s8_s16()` retains `arm_nn_softmax_common_s8()` (6,752
bytes), while the ET int8-only path uses the M55-optimized `arm_softmax_s8()`.

## Why some difference will remain

The specialized registrations use the same generic `Init` and `Prepare` functions,
with narrower evaluation functions. TFLM still computes quantization parameters,
requests scratch buffers, and handles general model metadata at initialization;
ET exports much of that work into the PTE. TFLM's int8 fully-connected evaluation
also includes per-channel quantization and a 1x1-convolution route. The ET linear
wrapper in these exports calls `arm_fully_connected_s8()` directly. TFLM computes
constant kernel sums at initialization; ET stores its sums in the model. These
are remaining implementation differences, not unused int4/int16 evaluation paths.

Recommendation: use the upstream int8 registrations wherever compatible before
publishing the next comparison, preserve the generic reshape, then rebuild both
TFLM profiles and validate outputs. New board timing remains deferred until the
cleaned ET DS-CNN export arrives. Existing archives and their published flash
numbers are unchanged by this audit.

Sources: generated resolvers in `build-e8-tflm-tiny-artifacts-v2/<model>/`, input-section
attribution in `size/<model>/memory-attribution.json` for both bundles;
`dependencies/tensorflow/tensorflow/lite/micro/micro_mutable_op_resolver.h`;
`dependencies/tensorflow/tensorflow/lite/micro/kernels/{conv,depthwise_conv,fully_connected,pooling,add,softmax}.h`;
the corresponding `kernels/cmsis_nn/*.cc`; `kernels/reshape.cc`;
`dependencies/cmsis-nn/Source/SoftmaxFunctions/arm_softmax_s8_s16.c`;
and the isolated ET checkout's `backends/cortex_m/ops/op_quantized_linear.cpp`.

## Implemented: TFLM v3

The [rebuilt results](e8_tflm_int8_registration_results.md) now measure this change:
operator flash falls by 53.9% for DS-CNN/VWW, 54.4% for ResNet8 and 34.7% for AD.
All eight images build; a Cortex-M55 probe confirms 32 exact output matches against
the generic registrations and checks that the specialized callbacks are selected.
The new report preserves separate silent and logged profile hashes and records the
remaining 848-byte INT16 pooling helper retained through shared quantized evaluation.
This audit's v2 byte counts remain the before-change baseline. Hardware reruns remain
deferred until the cleaned ET DS-CNN export arrives.
