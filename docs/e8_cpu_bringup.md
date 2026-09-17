<!--
SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates <open-source-office@arm.com>
SPDX-License-Identifier: Apache-2.0
-->

# E8 CPU inference runner bring-up

Both frameworks build for the E8 M55-HP with the NPU disabled. These first images use
different small test networks to validate the build and boot paths. Their timings and
firmware sizes are **not an MLPerf Tiny comparison**. Both frameworks have completed
board smoke runs with cycle output: TFLM 159,234 cycles and ExecuTorch 14,304 then 14,639
cycles across two boots at 400 MHz, using different models. See the
[board results](e8_board_smoke_test.md#first-tflm-board-result) and
[comparison plan](e8_cpu_mlperf_tiny_plan.md) for subsequent work.
The [Bloaty comparison](e8_bloaty_comparison.md) breaks down the selective images by
source file and symbol, including shared toolchain and platform overhead.
The [logging and primitive-selection experiment](e8_logging_prim_comparison.md) records
the smaller logging-off images and their build settings. Active E8 and native builds
have logging enabled again for benchmark output, with primitive selection retained.
The active runners now include [repeatable benchmark mode](e8_cpu_benchmark.md); use its
new bundle for first-inference timing, warm-ups, and 100-sample statistics. The previously
validated one-inference smoke bundle remains unchanged.

## Frozen dependencies

| Component | Revision used |
| --- | --- |
| Repository base | `91de84c8f0e6c24678e48d661f5861cdcb280b70`, plus this branch's changes |
| TFLM | `50b720726a25e39bc381187b0dd39669ac425262` |
| ExecuTorch runtime and exporter | `80115201ee50342118b0a782ff7fa46a6fd67f97` (`1.6.0+8011520`) |
| CMSIS-NN, including export bindings | `v8.0.0`, `13c97dbb6f781d4aab38ed34e6e441f42b79aff4` |
| Arm GNU Toolchain | `15.2.Rel1`, GCC `15.2.1` |
| Python / CMake | `3.12.13` / `3.30.5` |
| PyTorch / TorchAO | `2.14.0+cpu` / `0.18.0.dev20260729+cpu` |

Framework revisions were resolved from upstream `main` when implementation started.
CMSIS-NN comes from the same local checkout for both firmware builds and ET's host bindings.
Both firmware builds use `-O3`, Cortex-M55, hard-float, and MVE. Armclang is deferred.

## Prepare the exporter

Run from the repository root, with the submodules at the revisions above. Use Python 3.12.
The commands below use `uv`, as in the validated environment. The ET Python build includes
its portable runtime and selective-build binding because the operator generator needs them.

```bash
uv venv resources_downloaded/env --python 3.12
uv pip install --python resources_downloaded/env/bin/python pip
resources_downloaded/env/bin/python set_up_default_resources.py \
  --ml-frameworks tflm --use-case inference_runner --skip-vela
source resources_downloaded/env/bin/activate

git -C dependencies/executorch submodule update --init --depth 1 -j8 \
  third-party/flatbuffers third-party/flatcc third-party/pybind11 \
  third-party/ao third-party/pocketfft third-party/gflags third-party/googletest \
  third-party/json backends/xnnpack/third-party/cpuinfo \
  backends/xnnpack/third-party/FXdiv backends/xnnpack/third-party/pthreadpool

uv pip install torch==2.14.0 --index-url https://download.pytorch.org/whl/test/cpu
uv pip install torchao==0.18.0.dev20260729 \
  --index-url https://download.pytorch.org/whl/nightly/cpu
uv pip install setuptools==78.1.0 wheel packaging pyyaml zstd certifi \
  patchelf pybind11 ruamel.yaml tabulate

export CMAKE_ARGS="\
-DEXECUTORCH_BUILD_XNNPACK=OFF \
-DEXECUTORCH_BUILD_KERNELS_OPTIMIZED=OFF \
-DEXECUTORCH_BUILD_PYBIND=ON \
-DEXECUTORCH_BUILD_EXTENSION_LLM=OFF \
-DEXECUTORCH_BUILD_EXTENSION_LLM_RUNNER=OFF \
-DEXECUTORCH_BUILD_EXTENSION_TRAINING=OFF \
-DEXECUTORCH_BUILD_COREML=OFF \
-DEXECUTORCH_BUILD_QNN=OFF \
-DEXECUTORCH_BUILD_OPENVINO=OFF \
-DEXECUTORCH_BUILD_KERNELS_LLM=OFF \
-DEXECUTORCH_BUILD_KERNELS_LLM_AOT=OFF \
-DEXECUTORCH_BUILD_KERNELS_CUSTOM_AOT=OFF \
-DEXECUTORCH_BUILD_KERNELS_QUANTIZED_AOT=OFF \
-DEXECUTORCH_BUILD_CMSIS_NN_PYBINDS=ON \
-DCMSIS_NN_LOCAL_PATH=$PWD/dependencies/cmsis-nn"
CMAKE_BUILD_PARALLEL_LEVEL=8 MAX_JOBS=8 \
  uv pip install --no-build-isolation --no-deps --editable dependencies/executorch
unset CMAKE_ARGS

python scripts/py/export_inference_runner_smoke.py
```

Use an existing environment by omitting `uv venv`. The source build intentionally uses
`--no-deps` after installing the versions above, to preserve the selected PyTorch packages.
The exported `smoke.json` records the source version, reference input/output, operators,
and planned buffers. `smoke-cortex-m.pte` has Cortex-M quantize, quantized-linear, and
dequantize operators with no delegates. `smoke-portable.pte` supports native wrapper tests.
These smoke models have floating-point boundaries around integer computation.

## Build both firmware images

Put the Arm GNU Toolchain's `bin` directory on `PATH` for configuration **and** building;
the post-link step invokes `arm-none-eabi-objcopy` by name. Activate the environment above.

```bash
export PATH="/path/to/arm-gnu-toolchain-15.2.rel1-x86_64-arm-none-eabi/bin:$PATH"

common=(
  -G Ninja
  -DTARGET_PLATFORM=alif -DTARGET_BOARD=DevKit-e8 -DTARGET_SUBSYSTEM=RTSS-HP
  -DCMAKE_TOOLCHAIN_FILE=scripts/cmake/toolchains/bare-metal-gcc.cmake
  -DCMAKE_BUILD_TYPE=Release -DLINKER_SCRIPT_NAME=RTSS-HP-infrun
  -DUSE_CASE_BUILD=inference_runner -DETHOS_U_NPU_ENABLED=OFF
  -DGLCD_UI=OFF -DALIF_CAMERA_ENABLED=OFF -DALIF_ISP_ENABLED=ON
  -DCPU_PROFILE_ENABLED=ON -DCONSOLE_UART=4 -DCMSIS_DSP_MIN_REQ_SRC_LIST=ON
  -DMLEK_LOG_ENABLE=ON -DHAL_LOG_ENABLE=ON
  '-DCMAKE_C_FLAGS_RELEASE=-O3 -g -DNDEBUG'
  '-DCMAKE_CXX_FLAGS_RELEASE=-O3 -g -DNDEBUG'
  -Dinference_runner_ACTIVATION_BUF_SZ=0x10000
)
cmake -S . -B build-e8-tflm-cpu "${common[@]}" \
  -DML_FRAMEWORK=TensorFlowLiteMicro \
  -DMLEK_TFLM_SELECTIVE_BUILD=ON \
  -Dinference_runner_MODEL_PATH="$PWD/resources_downloaded/inference_runner/dnn_s_quantized.tflite"
cmake --build build-e8-tflm-cpu --target mlek_inference_runner -j8

cmake -S . -B build-e8-et-cpu "${common[@]}" \
  -DML_FRAMEWORK=ExecuTorch -DML_FWK_TMP_MEM_SIZE=0x10000 \
  -DMLEK_EXECUTORCH_SELECTIVE_BUILD=ON -DMLEK_EXECUTORCH_SELECT_PRIM_OPS=ON \
  -Dinference_runner_MODEL_PATH="$PWD/resources_downloaded/inference_runner/smoke-cortex-m.pte"
cmake --build build-e8-et-cpu --target mlek_inference_runner -j8
```

The minimal CMSIS-DSP source list excludes unused functions; GCC 15.2 hit an internal compiler
error in the full library's `arm_atan2_q31`. ISP build support stays enabled because this DFP's
ISP driver fails to compile with `ALIF_ISP_ENABLED=OFF`; camera use is disabled.

Each build produces `bin/mlek_inference_runner.axf`, its `.map`, and
`bin/sectors/inference_runner/mram.bin`. The ELF contains debug symbols; the MRAM binary is
the application payload for Alif SETOOLS. The linker maps confirm:

| Buffer | Address | Reserved size |
| --- | --- | --- |
| TFLM arena or ET method/planned/input pool | `0x02000000` (SRAM) | 64 KiB |
| ET temporary pool | `0x02010000` (SRAM) | 64 KiB |
| Stack top | `0x20100000` (end of HP DTCM) | 32 KiB stack |

HP DTCM is 1 MiB in the E8 DFP's `soc_features.h` and `app_mem_regions.h`. The GNU runner
linker script has been corrected to match. DTCM arenas and ET memory spanning multiple banks
remain separate experiments. Increase the two pool sizes as needed for future models.

## ExecuTorch selective build

`MLEK_EXECUTORCH_SELECTIVE_BUILD=ON` selects registrations from
`inference_runner_MODEL_PATH` across portable, quantized, and Cortex-M operators.
The selected registration library references the kernel archives directly, allowing the
linker to omit unused kernel objects. Full Cortex-M and quantized registration libraries
are no longer linked. Compiler optimization remains `-O3`; dtype selection is not enabled.

The same operator list drives ExecuTorch's generated registry-capacity header. The Cortex-M
smoke model selects three operators: `cortex_m::quantize_per_tensor.out`,
`cortex_m::quantized_linear.out`, and `cortex_m::dequantize_per_tensor.out`.
`MLEK_EXECUTORCH_SELECT_PRIM_OPS=ON` (the default within selective builds) also selects
primitives from that list. This model needs none, giving three registry slots and
36 bytes of DTCM registry storage. Set that option to `OFF` to retain all 28 primitives
and the earlier 31-slot, 372-byte registry. Ordinary operator selection remains enabled.
The generated files under `build-e8-et-cpu/mlek-app/inference_runner_portable_ops_lib/` are:

- `selected_operators.yaml`: selected model operators and kernel metadata.
- `executorch/runtime/kernel/selected_max_kernel_num.h`: generated registry capacity.
- `prim_ops/selected_prim_ops.h`: upstream-generated primitive selection macros.

Selected registrations are in `RegisterCodegenUnboxedKernelsEverything.cpp` in the sibling
directories with `_portable`, `_quantized`, and `_cortex_m` suffixes. Separate generators
avoid collisions between Cortex-M and quantized schema names.

Initial E8 M55-HP measurements for `smoke-cortex-m.pte`, with GCC `-O3`, logging enabled,
and primitive selection disabled (the preserved selective artifact baseline):

| Item | Generic build | Selective build | Reduction |
| --- | ---: | ---: | ---: |
| MRAM application image | 506,036 B | 289,188 B | 216,848 B (42.9%) |
| DTCM registry storage | 24,000 B | 372 B | 23,628 B (98.5%) |
| DTCM `.bss` | 27,528 B | 3,912 B | 23,616 B |
| DTCM initialized data | 5,596 B | 5,468 B | 128 B |

The 64 KiB SRAM method pool, 64 KiB SRAM temporary pool, 64 KiB DTCM heap,
and 32 KiB DTCM stack retain their original sizes and memory banks. These are link-time
reservations. The current primitive-selected build has now run on the E8, reporting
1,565 bytes peak method-pool usage and 166 bytes peak temporary-pool usage; see the
[ET board result](e8_board_smoke_test.md#first-executorch-board-result). Stack and heap
high-water marks remain unmeasured.

The option defaults to `OFF` to preserve other use cases. It currently requires
`USE_CASE_BUILD=inference_runner`, since all executables in a build tree share the runtime
registry. It also works for native tests using a portable `.pte`. Replacing the model at
the same path triggers regeneration of both its embedded bytes and registrations.
Reconfigure with `-DMLEK_EXECUTORCH_SELECTIVE_BUILD=OFF` to restore the generic libraries.
Local regression checks cover both settings, automatic regeneration after replacing the
PTE at the same path, and a manual registry-capacity override. Primitive selection is also
checked with a model requiring `executorch_prim::et_view.default`, which passes native
inference tests with that primitive retained.

An explicit `-DMAX_KERNEL_NUM=N` overrides automatic capacity, following ExecuTorch's
semantics; it must cover every registered kernel, including runtime primitives. Leave it
unset for automatic sizing (`cmake -U MAX_KERNEL_NUM ...` removes a cached override).
Do not combine this integration with upstream `EXECUTORCH_SELECT_OPS_*` options or
`EXECUTORCH_ENABLE_DTYPE_SELECTIVE_BUILD`; those are separate build paths.

These footprint reductions compare the same ET model before and after selection. TFLM now
has corresponding model-specific selection, described below. The two smoke networks remain
different; cross-framework size comparisons still require equivalent MLPerf Tiny models.

## TFLM selective build

`MLEK_TFLM_SELECTIVE_BUILD=ON` generates an inference-runner model class containing a
`MicroMutableOpResolver` sized for the distinct builtin operators used by the `.tflite`.
It scans operators in every subgraph, deduplicates registrations across operator versions,
and reads the available `Add*` methods from the selected TFLM checkout. Fused activations
remain part of their parent operator. Unreferenced entries in the opcode table are omitted.

The generator uses the existing Vela flatbuffer parser (`ethos-u-vela`, or the Python
package's `[tflite]` extra); a full TensorFlow installation is not required. Unsupported
builtins and custom operators fail configuration with an error. Dynamic model loading
cannot be combined with this option. It defaults to `OFF`; use that setting to retain the
generic resolver. The selected model class belongs to the application, leaving the shared
framework library independent of this use case and its generated files.

For `dnn_s_quantized.tflite`, the four selected operators are `DEQUANTIZE`,
`FULLY_CONNECTED`, `QUANTIZE`, and `SOFTMAX`. The generated files are:

- `build-e8-tflm-cpu/generated/inference_runner/include/SelectedTflmModel.hpp`
- `build-e8-tflm-cpu/generated/inference_runner/include/selected_tflm_operators.json`

The JSON records the model hash, operator versions, registration methods, and capacity.
Changing the model at the same path regenerates both the resolver and embedded model bytes.

Measured E8 M55-HP footprints for the identical model, with GCC `-O3` and CMSIS-NN 8.0.0:

| Item | Generic build | Selective build | Reduction |
| --- | ---: | ---: | ---: |
| MRAM application image | 835,156 B | 344,308 B | 490,848 B (58.8%) |
| Resolver capacity | 98 | 4 | 94 slots |
| Resolver object | 3,540 B | 156 B | 3,384 B |
| Model wrapper, including resolver | 3,604 B | 220 B | 3,384 B |
| DTCM initialized data | 5,064 B | 5,060 B | 4 B |
| DTCM `.bss` | 3,448 B | 3,384 B | 64 B |

The resolver is a member of the model object on `MainLoop`'s DTCM stack. Its smaller size
reduces the storage needed within that stack; the reserved 32 KiB stack is unchanged, and
these `sizeof` measurements are not peak stack measurements. The 64 KiB SRAM arena and
64 KiB DTCM heap are also unchanged. Unused kernel objects and the generic resolver are
absent from the firmware link. Native tests compare selective and generic outputs byte
for byte across three input patterns; the test binary intentionally links both resolvers.

Run the generator's focused unit tests with the environment activated:

```bash
python -m unittest discover -s tests/py -p test_gen_tflm_resolver.py -v
```

## Local checks and transfer

For the first load from macOS, follow the [board smoke test](e8_board_smoke_test.md),
including the DevKit-E8 SW4 positions for SE programming and UART4 output.

Native builds use `-DTARGET_PLATFORM=native`, `-DUSE_CASE_BUILD=inference_runner`, and the
corresponding framework/model options above, with `smoke-portable.pte` for ET. Run
`ctest --test-dir <build-directory> --output-on-failure` after building. Native timings are
host timings and do not estimate E8 performance.

Validated locally: both firmware links, both native runner executions, both native CTest
suites, ET reconstruction/repeated invocation, and the portable C++ runtime's output against
the exported PyTorch reference. Both linked firmware images include CMSIS-NN fully connected
kernels and MVE instructions. The ET image has no Ethos-U delegate or core-driver dependency.

Transfer the artifact archive to the E8 host and verify `SHA256SUMS` after extraction.
The frozen smoke bundle with **logging enabled and primitive selection retained** is
`build-artifacts/e8-cpu-logged-selective-bringup.tar.gz`. Earlier snapshots are preserved:
`e8-cpu-both-selective-bringup.tar.gz` has both frameworks selective but all ET primitives;
`e8-cpu-selective-bringup.tar.gz` has selective ET and generic TFLM;
`e8-cpu-bringup.tar.gz` has the original generic builds.
Load one framework at a time on **M55-HP**, keeping the other application core inactive.
The raw MRAM image is linked at **`0x80008000`**; select the matching HP boot configuration.
Use the board host's existing Alif SETOOLS or debugger workflow, following
[the standalone deployment instructions](../ML_Embedded_Evaluation_Kit.md#running-the-applications-standalone-without-debuggers).
The archive contains application images, not a generated Secure Enclave boot package.

Capture UART4 at **115200, 8N1** from reset. Look for successful model initialization,
`Inference completed.`, and a `CPU TOTAL` cycle result. Keep that log with the image's hash.
The smoke bundle performs one invocation with generated finite input. The new benchmark bundle
adds warm-ups and repeated measurements; both frameworks have completed three benchmark
boots. Means span 11.37–11.44 µs for ET and 374.16–374.38 µs for TFLM at 400 MHz, using
different smoke networks. Known-input board checks and equivalent Tiny model pairs remain
pending. See [the benchmark results](e8_cpu_benchmark.md).
