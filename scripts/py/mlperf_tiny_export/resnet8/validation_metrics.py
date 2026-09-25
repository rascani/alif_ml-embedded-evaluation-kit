# SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates
# <open-source-office@arm.com>
# SPDX-License-Identifier: Apache-2.0
"""Accuracy summaries shared by the TensorFlow and Torch validation stages."""

import numpy as np


def accuracy(outputs, dataset):
    predictions = outputs.argmax(axis=1)
    labels = dataset["labels"]
    groups = {
        "all_test": np.arange(len(labels)),
        "held_out": dataset["held_out_indices"],
        "reference_200": dataset["evaluation_indices"],
        "reference_without_calibration": np.setdiff1d(
            dataset["evaluation_indices"], dataset["calibration_indices"]
        ),
    }
    return {
        name: {
            "correct": int(np.sum(predictions[indices] == labels[indices])),
            "samples": len(indices),
            "accuracy_percent": float(
                np.mean(predictions[indices] == labels[indices]) * 100
            ),
        }
        for name, indices in groups.items()
    }
