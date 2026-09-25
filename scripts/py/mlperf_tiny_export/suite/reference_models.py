# SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates
# <open-source-office@arm.com>
# SPDX-License-Identifier: Apache-2.0
"""Strictly import every trained Keras tensor into the aligned Torch models."""

import json

import numpy as np
import torch
from executorch.examples.models.mlperf_tiny.deep_autoencoder import DeepAutoEncoder
from executorch.examples.models.mlperf_tiny.ds_cnn import DSCNNKWS
from executorch.examples.models.mlperf_tiny.mobilenet_v1_025 import MobileNetV1025


def layer_mapping(name):
    """Return Torch module names and their Keras layer names, in execution order."""
    if name == "deep_autoencoder":
        result = []
        for i in range(9):
            suffix = f"_{i}" if i else ""
            result.extend(
                [
                    (f"encoder_decoder.{3*i}", f"dense{suffix}"),
                    (f"encoder_decoder.{3*i+1}", f"batch_normalization{suffix}"),
                    (f"encoder_decoder.{3*i+2}", f"activation{suffix}"),
                ]
            )
        return result + [("output_layer", "dense_9")]
    assert name in ("ds_cnn", "mobilenet_v1_025")
    stem = "feature_extractor" if name == "ds_cnn" else "stem"
    result = [
        (f"{stem}.0", "conv2d"),
        (f"{stem}.1", "batch_normalization"),
        (f"{stem}.2", "activation"),
    ]
    if name == "ds_cnn":
        result.append(("feature_extractor.3", "dropout"))
    for i in range(4 if name == "ds_cnn" else 13):
        block = f"feature_extractor.{i+4}" if name == "ds_cnn" else f"features.{i}"
        suffix = f"_{i}" if i else ""
        result.extend(
            [
                (f"{block}.depthwise", f"depthwise_conv2d{suffix}"),
                (f"{block}.depthwise_bn", f"batch_normalization_{2*i+1}"),
                (f"{block}.relu", f"activation_{2*i+1}"),
                (f"{block}.pointwise", f"conv2d_{i+1}"),
                (f"{block}.pointwise_bn", f"batch_normalization_{2*i+2}"),
                (f"{block}.relu", f"activation_{2*i+2}"),
            ]
        )
    if name == "ds_cnn":
        result.append(("feature_extractor.8", "dropout_1"))
    result.append(("pool" if name == "ds_cnn" else "avgpool", "average_pooling2d"))
    return result + [("classifier", "dense")]


def load_reference_model(name, reference_dir, *, match_epsilon=True):
    model = {
        "ds_cnn": lambda: DSCNNKWS(apply_softmax=True),
        "mobilenet_v1_025": lambda: MobileNetV1025(apply_softmax=True),
        "deep_autoencoder": DeepAutoEncoder,
    }[name]().eval()
    weights = np.load(reference_dir / "keras_weights.npz", allow_pickle=False)
    layers = {
        layer["name"]: layer
        for layer in json.loads((reference_dir / "keras_model.json").read_text())
    }
    copied, used, batchnorms, epsilon_changes = {}, set(), [], []
    for module_name, layer_name in layer_mapping(name):
        module = model.get_submodule(module_name)
        layer = layers[layer_name]
        config, keys = layer["config"], layer["weight_keys"]
        if isinstance(module, torch.nn.Conv2d):
            expected = "DepthwiseConv2D" if module.groups > 1 else "Conv2D"
            assert layer["class"] == expected
            assert (
                config["activation"] == "linear"
                and config["data_format"] == "channels_last"
            )
            assert tuple(config["strides"]) == module.stride
            assert tuple(config["dilation_rate"]) == module.dilation
            assert config["use_bias"] and len(keys) == 2
            kernel = torch.from_numpy(weights[keys[0]])
            if expected == "DepthwiseConv2D":
                assert config["depth_multiplier"] == 1
                kernel = kernel.permute(2, 3, 0, 1)
            else:
                kernel = kernel.permute(3, 2, 0, 1)
            copied[f"{module_name}.weight"] = kernel.contiguous()
            copied[f"{module_name}.bias"] = torch.from_numpy(weights[keys[1]])
        elif isinstance(module, (torch.nn.BatchNorm1d, torch.nn.BatchNorm2d)):
            assert (
                layer["class"] == "BatchNormalization"
                and config["center"]
                and config["scale"]
            )
            assert config["axis"] in (-1, 1, 3, [-1], [1], [3]) and len(keys) == 4
            for attribute, key in zip(
                ("weight", "bias", "running_mean", "running_var"), keys
            ):
                copied[f"{module_name}.{attribute}"] = torch.from_numpy(weights[key])
            batchnorms.append(module_name)
            epsilon_changes.append(
                {
                    "module": module_name,
                    "torch_default": module.eps,
                    "reference": config["epsilon"],
                }
            )
            if match_epsilon:
                module.eps = float(config["epsilon"])
        elif isinstance(module, torch.nn.Linear):
            assert layer["class"] == "Dense" and config["use_bias"] and len(keys) == 2
            assert config["activation"] == (
                "softmax" if module_name == "classifier" else "linear"
            )
            copied[f"{module_name}.weight"] = torch.from_numpy(
                weights[keys[0]]
            ).T.contiguous()
            copied[f"{module_name}.bias"] = torch.from_numpy(weights[keys[1]])
        else:
            assert not keys, layer_name
        assert not set(keys) & used, layer_name
        used.update(keys)
    assert used == set(weights.files), set(weights.files) - used
    state = model.state_dict()
    assert set(state) - set(copied) == {
        f"{name}.num_batches_tracked" for name in batchnorms
    }
    for key, value in copied.items():
        assert value.shape == state[key].shape and value.dtype == state[key].dtype, key
        state[key] = value
    model.load_state_dict(state, strict=True)
    return model, epsilon_changes


class NHWCInput(torch.nn.Module):
    def __init__(self, model):
        super().__init__()
        self.model = model

    def forward(self, x):
        return self.model(x.permute(0, 3, 1, 2))
