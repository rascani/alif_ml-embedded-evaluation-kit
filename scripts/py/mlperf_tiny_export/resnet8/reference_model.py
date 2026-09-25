# SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates
# <open-source-office@arm.com>
# SPDX-License-Identifier: Apache-2.0
"""Import the reference FP32 checkpoint into the existing Torch ResNet8 model."""

import json

import numpy as np
import torch
from executorch.examples.models.mlperf_tiny.resnet8 import ResNet8


CONVOLUTIONS = [
    ("entry.0", "conv2d"),
    ("stages.0.path_a.0", "conv2d_1"),
    ("stages.0.path_a.3", "conv2d_2"),
    ("stages.1.path_a.0", "conv2d_3"),
    ("stages.1.path_a.3", "conv2d_4"),
    ("stages.1.skip", "conv2d_5"),
    ("stages.2.path_a.0", "conv2d_6"),
    ("stages.2.path_a.3", "conv2d_7"),
    ("stages.2.skip", "conv2d_8"),
]
BATCHNORMS = [
    ("entry.1", "batch_normalization"),
    ("stages.0.path_a.1", "batch_normalization_1"),
    ("stages.0.path_a.4", "batch_normalization_2"),
    ("stages.1.path_a.1", "batch_normalization_3"),
    ("stages.1.path_a.4", "batch_normalization_4"),
    ("stages.2.path_a.1", "batch_normalization_5"),
    ("stages.2.path_a.4", "batch_normalization_6"),
]


def load_reference_model(reference_dir, *, match_epsilon=True):
    weights = np.load(reference_dir / "keras_weights.npz", allow_pickle=False)
    layers = {
        layer["name"]: layer
        for layer in json.loads((reference_dir / "keras_model.json").read_text())
    }
    model = ResNet8(apply_softmax=True).eval()
    copied, used, epsilon_changes = {}, set(), []
    for module_name, layer_name in CONVOLUTIONS:
        module = model.get_submodule(module_name)
        layer = layers[layer_name]
        config = layer["config"]
        assert layer["class"] == "Conv2D" and config["activation"] == "linear"
        assert config["data_format"] == "channels_last" and config["padding"] == "same"
        assert tuple(config["strides"]) == module.stride
        assert tuple(config["dilation_rate"]) == module.dilation
        keys = layer["weight_keys"]
        assert len(keys) == 2 and config["use_bias"]
        copied[f"{module_name}.weight"] = (
            torch.from_numpy(weights[keys[0]]).permute(3, 2, 0, 1).contiguous()
        )
        copied[f"{module_name}.bias"] = torch.from_numpy(weights[keys[1]])
        used.update(keys)
    for module_name, layer_name in BATCHNORMS:
        module = model.get_submodule(module_name)
        layer = layers[layer_name]
        config = layer["config"]
        assert (
            layer["class"] == "BatchNormalization"
            and config["center"]
            and config["scale"]
        )
        assert config["axis"] in (3, -1, [3], [-1])
        keys = layer["weight_keys"]
        assert len(keys) == 4
        for name, key in zip(["weight", "bias", "running_mean", "running_var"], keys):
            copied[f"{module_name}.{name}"] = torch.from_numpy(weights[key])
        used.update(keys)
        epsilon_changes.append(
            {
                "module": module_name,
                "torch_default": module.eps,
                "reference": config["epsilon"],
            }
        )
        if match_epsilon:
            module.eps = float(config["epsilon"])
    dense = layers["dense"]
    assert dense["class"] == "Dense" and dense["config"]["activation"] == "softmax"
    keys = dense["weight_keys"]
    assert len(keys) == 2 and dense["config"]["use_bias"]
    copied["head.weight"] = torch.from_numpy(weights[keys[0]]).T.contiguous()
    copied["head.bias"] = torch.from_numpy(weights[keys[1]])
    used.update(keys)
    assert used == set(weights.files)
    state = model.state_dict()
    assert set(state) - set(copied) == {
        f"{name}.num_batches_tracked" for name, _ in BATCHNORMS
    }
    for name, value in copied.items():
        assert (
            value.dtype == state[name].dtype and value.shape == state[name].shape
        ), name
        state[name] = value
    model.load_state_dict(state, strict=True)
    return model, epsilon_changes


class NHWCInput(torch.nn.Module):
    def __init__(self, model):
        super().__init__()
        self.model = model

    def forward(self, x):
        return self.model(x.permute(0, 3, 1, 2))
