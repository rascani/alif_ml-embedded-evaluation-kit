/*
 * SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates
 * <open-source-office@arm.com>
 * SPDX-License-Identifier: Apache-2.0
 */
#ifndef MLEK_INFERENCE_RUNNER_MODEL_HPP
#define MLEK_INFERENCE_RUNNER_MODEL_HPP

#if defined(MLEK_TFLM_SELECTIVE_BUILD)
#include "SelectedTflmModel.hpp"
#else
#include "mlek/fwk/tflm/TestModel.hpp"
#endif

namespace arm::app::inference_runner {

#if defined(MLEK_TFLM_SELECTIVE_BUILD)
using TflmInferenceModel = SelectedTflmModel;
#else
using TflmInferenceModel = fwk::tflm::TestModel;
#endif

} // namespace arm::app::inference_runner

#endif // MLEK_INFERENCE_RUNNER_MODEL_HPP
