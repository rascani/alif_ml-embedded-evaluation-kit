# SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates
# <open-source-office@arm.com>
# SPDX-License-Identifier: Apache-2.0
"""Task quality on named, explicitly indexed subsets of the frozen inputs."""

import numpy as np


def quality(outputs, dataset, output_quantization=None):
    if output_quantization is not None:
        outputs = (
            outputs.astype(np.float32) - output_quantization["zero_point"]
        ) * output_quantization["scale"]
    report = {}
    for group in ("evaluation", "held_out", "reference", "calibration"):
        indices = dataset[f"{group}_indices"]
        if not len(indices):
            continue
        labels = dataset["labels"][indices]
        if outputs.shape[1] != 640:
            correct = int(np.sum(outputs[indices].argmax(1) == labels))
            report[group] = {
                "samples": len(indices),
                "correct": correct,
                "accuracy_percent": 100 * correct / len(indices),
            }
        else:
            errors = np.mean(
                (outputs[indices].astype(np.float64) - dataset["inputs"][indices]) ** 2,
                axis=1,
            )
            names = dataset["recording_ids"][indices]
            machine_ids = dataset["machine_ids"][indices]
            scores, truth, machines = [], [], []
            for name in np.unique(names):
                selected = names == name
                assert (
                    len(np.unique(labels[selected]))
                    == len(np.unique(machine_ids[selected]))
                    == 1
                )
                scores.append(float(errors[selected].mean()))
                truth.append(int(labels[selected][0]))
                machines.append(str(machine_ids[selected][0]))
            scores, truth, machines = (
                np.array(scores),
                np.array(truth),
                np.array(machines),
            )
            by_machine = {}
            for machine in np.unique(machines):
                positive = scores[(machines == machine) & (truth == 1)]
                negative = scores[(machines == machine) & (truth == 0)]
                if len(positive) and len(negative):
                    by_machine[machine] = float(
                        np.mean(
                            (positive[:, None] > negative).astype(np.float64)
                            + 0.5 * (positive[:, None] == negative)
                        )
                    )
            report[group] = {
                "windows": len(indices),
                "recordings": len(scores),
                "auc_by_machine": by_machine,
            }
            if by_machine:
                positive, negative = scores[truth == 1], scores[truth == 0]
                report[group].update(
                    macro_auc=float(np.mean(list(by_machine.values()))),
                    pooled_auc=float(
                        np.mean(
                            (positive[:, None] > negative).astype(np.float64)
                            + 0.5 * (positive[:, None] == negative)
                        )
                    ),
                )
    return report
