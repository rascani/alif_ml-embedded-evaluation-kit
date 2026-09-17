<!--
SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates <open-source-office@arm.com>
SPDX-License-Identifier: Apache-2.0
-->

# E8 board smoke test from macOS

Use the frozen `e8-cpu-logged-selective-bringup.tar.gz` bundle to check programming,
boot, UART output, and one CPU inference on M55-HP. Start with TFLM, then repeat with
ExecuTorch. These images contain their smoke models and generated input; no new
MLPerf models, camera, audio input, or external model-file programming is required.
For the new first-inference/warm-up/repeated-measurement images, see
[the CPU benchmark guide](e8_cpu_benchmark.md).

The user has successfully loaded and run both **TFLM and ExecuTorch** smoke images on
the E8; both reported logs include successful inference and cycle output.
Two ET smoke boots have completed successfully with identical allocator usage. Both frameworks
have also completed three boots of their newer benchmark images, establishing repeated-boot
operation; see [the benchmark results](e8_cpu_benchmark.md). The Mac's SE Tools installation is
`/Users/rja/app-release-exec-macos`, with `app-gen-toc` version **0.35.000**.
The observed USB serial candidate is `/dev/cu.usbmodem0012192765291`.
The supplied toolkit example references signed `app-device-config.json`, version
`0.5.00`; the smoke configurations preserve that `DEVICE` entry.

## First TFLM board result

The user-provided UART log reports:

| Item | Observed value |
| --- | ---: |
| Processor clock | 400,000,000 Hz |
| Tensor arena used | 4,160 bytes of the reserved 65,536 bytes |
| Inference count | 1 |
| CPU TOTAL | 159,234 cycles |
| Time derived from reported clock | 398.085 microseconds |
| Completion | `Inference completed.` followed by `program terminating...` |

This confirms the TFLM programming/boot/inference/logging workflow. It is one smoke
measurement, not an accuracy check or a matched MLPerf Tiny benchmark. The original
terminal display showed staircase indentation because the firmware's bulk UART
write path emits LF without adding CR; use the capture method below for readable output.

## First ExecuTorch board result

The user-provided UART log reports:

| Item | Observed value |
| --- | ---: |
| Processor clock | 400,000,000 Hz |
| Embedded PTE size | 3,040 bytes |
| Method pool | 1,565 bytes used/peak of 65,536 reserved at `0x02000000` |
| Temporary pool | 0 bytes used; 166 bytes peak of 65,536 reserved at `0x02010000` |
| Inference count | 1 |
| CPU TOTAL | 14,304 cycles |
| Time derived from reported clock | 35.76 microseconds |
| Completion | `Inference completed.` followed by `program terminating...` |

The method pool's 1,565 bytes include the 80-byte planned buffer, 1,417 bytes allocated
while loading the method, and 68 bytes allocated while preparing input. These are
allocator usage figures, not total application RAM: the firmware still reserves both
64 KiB pools, plus its separate stack, heap, and static data. The temporary peak is
already 166 bytes before inference and remains unchanged afterward; it is a lifetime
high-water mark, not an isolated inference scratch measurement.

The log lists `cortex_m::quantize_per_tensor.out`, `cortex_m::quantized_linear.out`, and
`cortex_m::dequantize_per_tensor.out`, with no delegates. This confirms successful
execution of the selected CPU operators in the primitive-selected smoke build.
The ET network has input shape `[1, 16]` and output shape `[1, 4]`; TFLM uses `[1, 250]`
and `[1, 12]`. Their times and allocator usage are not a matched framework comparison.
Known-input output validation remains pending.

The ET capture announcement named `/Users/rja/alif/logs/tflm/tflm-uart.log`. Since the
helper appends, that file may contain both frameworks. Preserve it and use the ET log
path below for subsequent resets.

### ExecuTorch repeat boot

A subsequent user-provided capture saved to `/Users/rja/alif/logs/et/et-uart.log`
confirms a second complete boot and inference with the same model, build banner,
400 MHz clock, operators, and allocator usage.

| Boot | CPU TOTAL | Time at reported clock | Method pool peak | Temporary pool peak |
| --- | ---: | ---: | ---: | ---: |
| First | 14,304 cycles | 35.7600 microseconds | 1,565 bytes | 166 bytes |
| Second | 14,639 cycles | 36.5975 microseconds | 1,565 bytes | 166 bytes |

The second result is 335 cycles (0.8375 microseconds, approximately 2.34%) higher.
Both runs report successful completion; these two single-invocation boot samples
do not establish a latency distribution or explain the variation. The newer benchmark
mode separates the first invocation from warm-ups and repeated measurements; its three
ET board runs are recorded in [the benchmark guide](e8_cpu_benchmark.md).

## 1. Verify the bundle on the Mac

Copy the archive to `/Users/rja/alif/`, then:

```bash
cd /Users/rja/alif
shasum -a 256 e8-cpu-logged-selective-bringup.tar.gz
tar -xzf e8-cpu-logged-selective-bringup.tar.gz
cd build-e8-cpu-logged-selective-artifacts
shasum -a 256 -c SHA256SUMS
```

The archive SHA-256 is:

```text
c8d41feeffed2566fb0aaacc8962e4d43d5d22ecee429daff8051502cf4392db
```

All checks in `SHA256SUMS` should report `OK`. Use the framework's `mram.bin` as the
SE Tools application input; its model is already embedded.

| Image | Size | Load address | Initial SP | Reset vector |
| --- | ---: | --- | --- | --- |
| `tflm/mram.bin` | 344,308 B | `0x80008000` | `0x20100000` | `0x80018ee5` |
| `et/mram.bin` | 275,140 B | `0x80008000` | `0x20100000` | `0x80010f99` |

The reset vectors above include the Thumb bit. They are diagnostics for these exact
images, not additional addresses to enter in the normal SE Tools boot configuration.

## 2. Identify the tool installation and connect the board

Use the board's required power supply and connect the Mac to **PRG USB (J3)**.
The DevKit-E8 board layer documents the following switch positions:

| Operation | SW4 position |
| --- | --- |
| SE Tools programming | **SE** |
| M55-HP application console on UART4 | **U4** |

Source: [DevKit-E8 M55-HP board layer](../dependencies/cmsis-alif/Boards/DevKit-e8/Layers/M55_HP/README.md).
The switch routes the programming/debug serial connection; do not assume two
separate Mac serial devices are required for these two uses.

From the installed SE Tools directory, collect:

```bash
cd /Users/rja/app-release-exec-macos
pwd
./app-gen-toc --help
ls build/config
ls /dev/cu.*
```

For the installed toolkit, also inspect its version, connection options, and example
application configuration:

```bash
./app-gen-toc -V
./maintenance --help
./app-write-mram --help
cat build/config/app-cfg.json
```

The supplied help confirms `maintenance -d` for discovery, and `app-write-mram -c`
for an explicit serial path. Use `/dev/cu.usbmodem0012192765291` for the first connection
attempt and confirm the tool recognizes **AE822FA0E5597LS0 / E8**. Close any serial
terminal before SE Tools opens the port.

## 3. Prepare the TFLM application package

Run from the SE Tools directory:

```bash
cp /Users/rja/alif/build-e8-cpu-logged-selective-artifacts/tflm/mram.bin \
  build/images/e8-smoke-tflm.bin
cp /Users/rja/alif/build-e8-cpu-logged-selective-artifacts/et/mram.bin \
  build/images/e8-smoke-et.bin
```

Copy [e8-smoke-tflm.json](setools/e8-smoke-tflm.json) into
`build/config/e8-smoke-tflm.json`. Its complete contents are:

```json
{
  "DEVICE": {
    "disabled": false,
    "binary": "app-device-config.json",
    "version": "0.5.00",
    "signed": true
  },
  "HP_Smoke": {
    "disabled": false,
    "binary": "e8-smoke-tflm.bin",
    "version": "1.0.0",
    "mramAddress": "0x80008000",
    "cpu_id": "M55_HP",
    "flags": ["boot"],
    "signed": false
  }
}
```

This preserves the toolkit example's `DEVICE` entry and boots only the M55-HP smoke
application. These images execute directly from MRAM, so the application uses
`mramAddress` and the `boot` flag. The toolkit's RAM-loaded blink example uses a
different loading mode. Keep `app-device-config.json` and the toolkit's signing
assets in their existing locations.

Generate the package and, only if generation succeeds, write it using the confirmed
command-line options:

```bash
./app-gen-toc -f build/config/e8-smoke-tflm.json &&
  ./app-write-mram -c /dev/cu.usbmodem0012192765291 -p
```

Set **SW4 to SE** for writing and follow the tool's connection/reset prompts. Generate
the package successfully before writing it; the write command uses the generated
application package. The documented `-p` option pads images to the required 16-byte
alignment. Both raw payload lengths need padding. Keep the original bundle unchanged.
Use elevated execution only if required by the installed toolkit and Mac permissions.

## 4. Capture the boot and inference result

After programming completes:

1. Close SE Tools' serial connection.
2. Move **SW4 to U4**.
3. Open the corresponding Mac serial device at **115200 baud, 8 data bits, no parity,
   one stop bit, no flow control**, with capture/logging enabled.
4. Reset the board **after the terminal is open**. This runner executes once per boot.

For the observed serial device (check the path again if USB is reconnected), use
[capture_uart.py](../scripts/py/capture_uart.py). Copy that file to `/Users/rja/alif/`.
It configures and reads the port through the same open handle. The earlier separate
`stty`/`cat` procedure produced garbled data on the Mac and is no longer recommended.

First close any existing `screen` session with `Ctrl-A`, then `K`, and confirm closing
it. If a failed capture has left the terminal unresponsive to Ctrl-C, close that tab
and open a fresh terminal. In the Mac's `(alif)` Python environment:

```bash
mkdir -p /Users/rja/alif/logs/tflm
python3 -m pip install pyserial==3.5
python3 /Users/rja/alif/capture_uart.py \
  --port /dev/cu.usbmodem0012192765291 \
  --output /Users/rja/alif/logs/tflm/tflm-uart.log
```

Keep SW4 at U4 and reset after the reader prints `Listening on ...`. It explicitly
sets 115200 8N1 with all flow control disabled, appends received bytes unchanged to
`tflm-uart.log`, and adds CR before LF for display. Stop capture with `Ctrl-C` before
using SE Tools again. The reader leaves the host terminal's input modes unchanged.
A GUI serial terminal with LF-to-CRLF display translation and file logging is
equally suitable.

The helper passed a local pseudo-terminal check of settings, raw log preservation,
newline display conversion, and Ctrl-C shutdown. The user also confirmed successful,
readable capture from the E8 on the Mac using this helper.

Look for the application banner, TFLM model/tensor details, and these result markers
(other profiling lines may appear between them):

```text
INFO - Final results:
INFO - Total number of inferences: 1
INFO - Profile for Inference:
INFO - CPU TOTAL: <nonzero count> cycles
INFO - Inference completed.
INFO - program terminating...
```

`program terminating...` after successful completion is expected for this one-shot
runner. It does not repeat automatically. Reset once more to check a second boot.
Record the complete serial log, image hash, and toolkit version. A cycle result checks
the measurement path; these generated-input smoke runs do not establish model accuracy
or comparable MLPerf Tiny performance.

## 5. Repeat for ExecuTorch

Copy [e8-smoke-et.json](setools/e8-smoke-et.json) to `build/config/e8-smoke-et.json`.
It uses the same device configuration, M55-HP core and `0x80008000` address, with
`e8-smoke-et.bin` as the application binary.

Close the serial terminal, switch SW4 to SE, generate/write the ET package, then
switch back to U4, open a new log under `/Users/rja/alif/logs/et/`, and reset.

Expect ExecuTorch initialization and the three `cortex_m::*` operator names, followed
by `CPU TOTAL` and `Inference completed.`. Repeat a reset. Passing both frameworks
establishes the copy → package → program → reset → capture workflow using the same core.

With the ET image already programmed, stop the old reader with Ctrl-C and capture
additional resets without reflashing:

```bash
mkdir -p /Users/rja/alif/logs/et
python3 /Users/rja/alif/capture_uart.py \
  --port /dev/cu.usbmodem0012192765291 \
  --output /Users/rja/alif/logs/et/et-uart.log
```

Keep SW4 at U4. After `Listening on ...`, reset twice, waiting for
`program terminating...` before the second reset. Retain both complete boot logs.

## Troubleshooting by the last successful step

| Symptom | First checks |
| --- | --- |
| Tool cannot connect | PRG USB cable/power, SW4 at SE, selected serial device, terminal closed, toolkit reset prompts |
| Package generation fails | Installed toolkit version, E8 device configuration, image filename under `build/images`, required vendor metadata |
| Programming succeeds but no output | SW4 at U4, 115200 8N1/no flow control, terminal opened before reset, HP boot flag and MRAM address |
| Each line starts farther to the right | LF-only firmware output; use `capture_uart.py` for display conversion |
| Sustained garbled data | Close the previous port owner, check SW4 at U4, and use the reader's persistent 115200 8N1 configuration |
| Banner appears, then initialization fails | Save the full log and confirm the image hash; inspect framework/operator or allocator errors before changing pools |
| Inference completes without `CPU TOTAL` | Confirm this logging-enabled bundle and its image hash; its firmware was built with `CPU_PROFILE_ENABLED=ON` |
| Output stops after `program terminating...` | Expected after the single inference; reset to repeat |

Do not infer numerical correctness from successful invocation alone. Known-input
output checks and matched Tiny workloads follow after this board workflow works.
