/*
 * SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates
 * <open-source-office@arm.com>
 * SPDX-License-Identifier: Apache-2.0
 */
#if defined(INFERENCE_VALIDATION)
#include "InferenceValidation.hpp"
#include "InferenceValidationData.hpp"
#include "mlek/log/log_macros.h"
#include <cstring>

#ifndef INFERENCE_VALIDATION_REFERENCE
#define INFERENCE_VALIDATION_REFERENCE "lowered_python_int8"
#endif

namespace arm::app::inference_runner {
bool ValidateInference(fwk::iface::Model& model)
{
    if (model.GetNumInputs() != 1 || model.GetNumOutputs() != 1) {
        return false;
    }
    auto input  = model.GetInputTensor(0);
    auto output = model.GetOutputTensor(0);
    if (input->Type() != fwk::iface::TensorType::INT8 ||
        output->Type() != fwk::iface::TensorType::INT8 ||
        input->Bytes() != sizeof(kValidationInputs[0]) ||
        output->Bytes() != sizeof(kValidationOutputs[0])) {
        printf_err("VALIDATION incompatible tensors\n");
        return false;
    }
    const size_t count = sizeof(kValidationInputs) / sizeof(kValidationInputs[0]);
    for (size_t index = 0; index < count; ++index) {
        std::memcpy(input->GetData(), kValidationInputs[index], input->Bytes());
        if (!model.RunInference()) {
            return false;
        }
        const bool equal =
            std::memcmp(output->GetData(), kValidationOutputs[index], output->Bytes()) == 0;
        info("VALIDATION sample index=%zu status=%s\n", index, equal ? "PASS" : "FAIL");
        if (!equal) {
            return false;
        }
    }
    info("VALIDATION summary count=%zu status=PASS reference=%s\n",
         count,
         INFERENCE_VALIDATION_REFERENCE);
    return true;
}
} // namespace arm::app::inference_runner
#endif
