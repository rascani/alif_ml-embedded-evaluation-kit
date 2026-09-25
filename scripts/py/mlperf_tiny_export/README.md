<!--
SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates <open-source-office@arm.com>
SPDX-License-Identifier: Apache-2.0
-->

# Export scripts used for the final E8 Tiny models

This is a source snapshot from `mlperf-tiny-trained-integer-pooling.zip`, the export
bundle used for the final ExecuTorch v8 SRAM measurements. The seven Python files
preserve their original contents and layout, with only SPDX header comments added.
[provenance.json](provenance.json) records original and copied source hashes, the
producer revision, package versions, patch identity, and expected PTE hashes.

| Models | Exporter |
| --- | --- |
| DS-CNN, MobileNetV1 0.25, deep autoencoder | [suite/export_trained.py](suite/export_trained.py) |
| ResNet8 | [resnet8/export_trained.py](resnet8/export_trained.py) |

Both exporters explicitly apply `QuantizeInputs` and `QuantizeOutputs` to `forward`,
assert INT8 input/output types in the serialized PTE, and use the Cortex-M55 explicit
layout passes. The three classifiers also use quantized softmax. The final PTEs have
no standalone Q/DQ operators. The separate `export_inference_runner_smoke.py` example
has floating-point I/O and did not produce these benchmark models.

## Requirements

Use the original ExecuTorch producer checkout at
`ae64c3c72e31445f3243f5e7811ab97b76ad27ca` with the bundle's
`provenance/model-alignment.patch` applied, and its prepared Python environment.
That checkout includes the DS-CNN Q/DQ fix and integer constant pooling. The recorded
versions are PyTorch `2.14.0+cpu`, torchao `0.18.0.dev20260729+cpu`, and CMSIS-NN
`13c97dbb6f781d4aab38ed34e6e441f42b79aff4` (8.0.0), including its Python bindings.
The exporters import the aligned model definitions from that ExecuTorch checkout.

The prepared `mlperf-tiny-e2e-audit` input tree is also required: each model's
`tensorflow/` contains `keras_weights.npz` and `keras_model.json`, and its float
validation directory contains `float-report.json`. ResNet8 uses `data/cifar10.npz`
and `data/dataset.json`; the other models use `data/dataset.npz`. The autoencoder
additionally uses `data/calibration-full.npy`. These files, source patches, and the
Python environment must accompany the original export artifacts for reproduction.
This source snapshot includes the exporters' local helper modules; it does not
download or prepare those external inputs.

## Original export invocations with configurable paths

Set absolute paths and choose a fresh output directory. Run from the producer
checkout because the exporters record its Git revision and source patch.

```bash
export TINY_EXPORT_SCRIPTS=/path/to/mlek/scripts/py/mlperf_tiny_export
export TINY_ET_TREE=/path/to/producer/executorch
export TINY_FROZEN_DATA=/path/to/mlperf-tiny-e2e-audit
export TINY_EXPORT_OUTPUT=/path/to/new-export
export TINY_PYTHON="$TINY_ET_TREE/cmake-out/venv/bin/python"
export PYTHONPATH="$TINY_ET_TREE/src:$TINY_EXPORT_SCRIPTS"
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2
cd "$TINY_ET_TREE"

"$TINY_PYTHON" "$TINY_EXPORT_SCRIPTS/resnet8/export_trained.py" \
  --data-dir "$TINY_FROZEN_DATA/resnet8/data" \
  --reference-dir "$TINY_FROZEN_DATA/resnet8/tensorflow" \
  --float-dir "$TINY_FROZEN_DATA/resnet8/torch" \
  --output-dir "$TINY_EXPORT_OUTPUT/resnet8/cortex-m55"

for model in ds_cnn mobilenet_v1_025; do
  "$TINY_PYTHON" "$TINY_EXPORT_SCRIPTS/suite/export_trained.py" \
    --model "$model" \
    --data-dir "$TINY_FROZEN_DATA/$model/data" \
    --reference-dir "$TINY_FROZEN_DATA/$model/tensorflow" \
    --float-dir "$TINY_FROZEN_DATA/$model/float" \
    --output-dir "$TINY_EXPORT_OUTPUT/$model/cortex-m55"
done

"$TINY_PYTHON" "$TINY_EXPORT_SCRIPTS/suite/export_trained.py" \
  --model deep_autoencoder \
  --data-dir "$TINY_FROZEN_DATA/deep_autoencoder/data" \
  --reference-dir "$TINY_FROZEN_DATA/deep_autoencoder/tensorflow" \
  --float-dir "$TINY_FROZEN_DATA/deep_autoencoder/float64" \
  --calibration-file "$TINY_FROZEN_DATA/deep_autoencoder/data/calibration-full.npy" \
  --calibration-batch-size 64 \
  --output-dir "$TINY_EXPORT_OUTPUT/deep_autoencoder/cortex-m55"
```

Compare the resulting PTE bytes and SHA-256 hashes with `expected_pte` in
`provenance.json`. Export also writes graphs, quantization parameters, Python
reference outputs and per-model manifests. Native output validation and packaging
are separate stages in the original bundle; the E8 firmware consumes the resulting
bundle through the [build workflow](../../../docs/e8_tiny_build_run.md).
