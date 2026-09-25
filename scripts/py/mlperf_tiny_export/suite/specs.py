# SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates
# <open-source-office@arm.com>
# SPDX-License-Identifier: Apache-2.0
"""Pinned reference checkpoint paths and batch-one model contracts."""

MODELS = {
    "ds_cnn": {
        "training": "keyword_spotting",
        "checkpoint": "kws_ref_model",
        "official": "kws_ref_model.tflite",
        "input_shape": (49, 10, 1),
        "output_size": 12,
        "softmax": True,
    },
    "mobilenet_v1_025": {
        "training": "visual_wake_words",
        "checkpoint": "vww_96.h5",
        "official": "vww_96_int8.tflite",
        "input_shape": (96, 96, 3),
        "output_size": 2,
        "softmax": True,
    },
    "deep_autoencoder": {
        "training": "anomaly_detection",
        "checkpoint": "ad01.h5",
        "official": "ad01_int8.tflite",
        "input_shape": (640,),
        "output_size": 640,
        "softmax": False,
    },
}
