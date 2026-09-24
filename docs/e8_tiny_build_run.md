<!--
SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates <open-source-office@arm.com>
SPDX-License-Identifier: Apache-2.0
-->

# E8 Tiny: build, program and collect

This workflow runs DS-CNN (`kws`), ResNet8 (`ic`), MobileNetV1 0.25 (`vww`) and the
deep autoencoder (`ad`) on the Alif E8 DevKit's Cortex-M55 HP with the NPU disabled.
Inference pools use SRAM; code and models use internal MRAM. The board reports
400 MHz. See the [measurement definitions](e8_tiny_methodology.md) when interpreting
the output and [timer validation](e8_timer_validation.md) for the counter check.

## Build prerequisites

Run build commands from the repository root. The measured configuration used GCC
15.2.1, Python 3.12, CMake 3.30.5, Ninja, and CMSIS-NN 8.0.0. Keep the checked-in
dependency pins when reproducing it. The build environment is
`resources_downloaded/env/`; it needs the project's Python tooling and, for ET,
the compatible source-built ExecuTorch Python package and host `flatc` executable.

```bash
git submodule update --init --recursive -j8
python3.12 -m venv resources_downloaded/env
source resources_downloaded/env/bin/activate
python -m pip install pip setuptools wheel
python set_up_default_resources.py \
  --ml-frameworks tflm --use-case inference_runner --skip-vela
python -m pip install -e 'scripts/py/[tflite]'

export GCC_BIN=/path/to/arm-gnu-toolchain-15.2.rel1-x86_64-arm-none-eabi/bin
export PATH="$GCC_BIN:$PATH"
```

Reuse an existing prepared environment by omitting its creation/setup commands.
The toolchain must remain on `PATH` during configuration and compilation because
post-link steps invoke `arm-none-eabi-objcopy` by name. The builders use a minimal
CMSIS-DSP source list; GCC 15.2 encounters an internal compiler error in an unused
function in the full library. Camera use is disabled while ISP build support stays
enabled for compatibility with the pinned Alif device pack.

## TFLM firmware

The builder downloads the models specified by `scripts/py/tflm_tiny_models.json`,
verifies their hashes, and runs native checks before building E8 images.

```bash
python scripts/py/build_tflm_tiny.py --gcc-bin "$GCC_BIN" --jobs 8 \
  --paired-profiles --bundle-name build-e8-tflm-tiny-current
```

`--paired-profiles` builds runtime/wrappers at `-Oz` and CMSIS kernels at `-O3`.
It produces logged latency/RAM images and separate silent size images. Without
this option, the builder uses its original logged `-O3` profile; those are different
compiler settings. Inspect `manifest.json` and `compiler-audit.json` for actual flags.

## ExecuTorch firmware

The four-model builder requires a separately supplied trained integer-pooling export
ZIP and the matching patched runtime checkout at
`resources_downloaded/et_tiny/executorch`. Its required Git tree is
`0510beb4b48b8785477a3c11b23c5bc18bd7841a`, based on commit
`9250dc3537862db4f66bac07a8974dad81cc0f20` plus staged backend/export patches.
The builder checks the staged tree and rejects unstaged changes. A tree hash is not
a fetchable commit. The MLEK ET submodule alone does not reconstruct this runtime;
obtain the matching source patches and Python environment with the export.

The final export's producer revision was
`ae64c3c72e31445f3243f5e7811ab97b76ad27ca`. Keep its PTEs, manifest, native int8
examples and checksum inventory together. The import step verifies and normalizes
these files without changing the PTEs. Use fresh output/bundle names for each run.

```bash
export EXPORT_ZIP=/path/to/mlperf-tiny-trained-integer-pooling.zip
python scripts/py/import_et_tiny_bundle.py --archive "$EXPORT_ZIP" \
  --output resources_downloaded/et_tiny/current-export
python scripts/py/build_et_tiny.py --gcc-bin "$GCC_BIN" --jobs 8 \
  --paired-profiles --export-dir resources_downloaded/et_tiny/current-export \
  --bundle-name build-e8-et-tiny-current
```

The builder embeds supplied validation examples for untimed output checking. It
retains runtime checks, model-specific operators and primitive selection. The
four final PTEs require no primitive registrations. Planned inputs use method-owned
storage directly; callers must refill them before every invocation because later
activations can reuse the same addresses.

For a new ET model outside the frozen four-model builder, use
`ML_FRAMEWORK=ExecuTorch` and `inference_runner_MODEL_PATH=/absolute/model.pte` in
the normal CMake workflow. Optional selection is controlled by
`MLEK_EXECUTORCH_SELECTIVE_BUILD=ON` and `MLEK_EXECUTORCH_SELECT_PRIM_OPS=ON`.
Selection currently requires `USE_CASE_BUILD=inference_runner`; it cannot be mixed
with upstream `EXECUTORCH_SELECT_OPS_*` or dtype-selection options. Replacing a PTE
at the same path regenerates its embedding and registrations. Leave `MAX_KERNEL_NUM`
unset for automatic capacity, or ensure an override covers every selected variant.

TFLM's corresponding optional controls are `MLEK_TFLM_SELECTIVE_BUILD=ON` and
`MLEK_TFLM_SELECT_INT8_OPS=ON`. INT8 callbacks are selected only when every node of
that operator is compatible and the callback exists; other cases retain the generic
callback. Custom operators require a custom resolver. Both frameworks use the same
local CMSIS-NN dependency. See its [compiler guidance](../dependencies/cmsis-nn/README.md).

## Artifacts and optional simulator checks

Each builder writes a new bundle directory and a verified `.tar.gz` plus `.sha256`
under `build-artifacts/`. The bundle includes `run.py`, its supporting modules,
`manifest.json`, `SHA256SUMS`, `flash.csv`, and per-model firmware, ELF, map, model,
selection metadata and placement evidence. Paired profiles put silent images under
`size/`; the top-level model directories contain the logged images used on the board.
New bundles include instructions, not measurements copied from earlier experiments.

The linker places a 256 KiB arena/method pool at `0x02000000` and ET's 64 KiB
temporary pool at `0x02040000`. These are capacities, not measured usage. Ordinary
globals, the 64 KiB heap and 32 KiB stack use DTCM. The HP linker capacity is 1 MiB.

Use `--no-package` to retain a build for additional checks. To run the supplied ET
validation harness, set `FVP` to a compatible Corstone-300 Cortex-M55 executable:

```bash
python scripts/py/validate_tiny_fvp.py --bundle build-e8-et-tiny-current \
  --build build-e8-et-tiny-oz-latency --gcc-bin "$GCC_BIN" --fvp "$FVP" --jobs 8
```

Simulator output checks validate execution and allocator observations, not E8 latency.
If adding validation files after a package was created, keep them separately or
regenerate a fresh package and checksum inventory; do not modify a frozen archive.

## Program and collect on the Mac

Install Alif SE Tools (the board workflow used 0.35.000) and PySerial 3.5. Copy the
bundle archive and checksum file to the Mac. Substitute the actual bundle, tool
directory and serial port below; the same commands work for either framework.

```bash
cd ~/alif
shasum -a 256 -c build-e8-et-tiny-current.tar.gz.sha256
tar -xzf build-e8-et-tiny-current.tar.gz
cd build-e8-et-tiny-current
python3 run.py verify
python3 run.py list
python3 run.py run all --tools "$HOME/app-release-exec-macos" \
  --port /dev/cu.YOUR_BOARD_PORT
python3 run.py collect
```

Close other serial readers. Follow the switch prompts: SW4 to **SE** for programming,
then **U4** for capture. The script preserves the installed SE Tools DEVICE entry and
boots M55-HP from MRAM at `0x80008000`. UART is 115200 baud, 8N1, without flow control.
Wait for `Listening`, then reset three times per model, waiting for completion between
resets. A boot reports 111 benchmark calls, 100 measured samples, memory information
and any ET saved-output checks. Identity, completeness, statistics and accounting
checks must pass before results are accepted.

Use `kws`, `ic`, `vww` or `ad` instead of `all` for one model. `run.py --help` lists
the tools, port, boot count and timeout overrides. To resume capture or reparse a
new attempt without mixing it with an interrupted run, give it a fresh log directory:

```bash
python3 run.py capture kws --port /dev/cu.YOUR_BOARD_PORT --logs logs/kws-new-pass
python3 run.py summarize kws --logs logs/kws-new-pass
```

`collect` prints a timestamped results archive containing the manifest, raw UART logs
and derived CSV/JSON. Copy it back into the build host's `build-artifacts/`. Keep
failed attempts separately and retain raw logs; never relabel old firmware results
as measurements of a new build. No board access is needed to rerun the parsers.
