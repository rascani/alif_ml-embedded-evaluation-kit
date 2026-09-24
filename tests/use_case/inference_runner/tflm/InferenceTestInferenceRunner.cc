/*
 * SPDX-FileCopyrightText: Copyright 2023, 2025-2026 Arm Limited and/or its affiliates
 * <open-source-office@arm.com> SPDX-License-Identifier: Apache-2.0
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
#include "BufAttributes.hpp"
#include "InferenceRunnerModel.hpp"
#include "mlek/fwk/tflm/TensorFlowLiteMicro.hpp"
#include "mlek/fwk/tflm/TestModel.hpp" /* Model class for running inference. */

#include <algorithm>
#include <catch.hpp>
#include <cstring>

namespace arm {
namespace app {
    static uint8_t tensorArena[ACTIVATION_BUF_SZ] ACTIVATION_BUF_ATTRIBUTE;
    namespace inference_runner {
        extern uint8_t* GetModelPointer();
        extern size_t GetModelLen();
    } /* namespace inference_runner */
} /* namespace app */
} /* namespace arm */

TEST_CASE("Testing Init failure due to insufficient tensor arena inf runner", "[inf runner]")
{
    arm::app::inference_runner::TflmInferenceModel model{};
    REQUIRE_FALSE(model.IsInited());
    size_t insufficientTensorArenaSz = 1000;
    arm::app::fwk::iface::MemoryRegion modelMem{arm::app::inference_runner::GetModelPointer(),
                                                arm::app::inference_runner::GetModelLen()};
    arm::app::fwk::iface::MemoryRegion computeMem{arm::app::tensorArena, insufficientTensorArenaSz};
    REQUIRE_FALSE(model.Init(computeMem, modelMem));
    REQUIRE_FALSE(model.IsInited());
}

#if defined(MLEK_TFLM_SELECTIVE_BUILD)
TEST_CASE("Selective TFLM resolver matches generic resolver outputs", "[inf runner][selective]")
{
    using namespace arm::app;
    alignas(16) static uint8_t referenceArena[ACTIVATION_BUF_SZ];
    fwk::iface::MemoryRegion modelMem{inference_runner::GetModelPointer(),
                                      inference_runner::GetModelLen()};
    fwk::iface::MemoryRegion computeMem{tensorArena, sizeof(tensorArena)};
    fwk::iface::MemoryRegion referenceMem{referenceArena, sizeof(referenceArena)};
    inference_runner::TflmInferenceModel selected;
    fwk::tflm::TestModel reference;
    REQUIRE(selected.Init(computeMem, modelMem));
    REQUIRE(reference.Init(referenceMem, modelMem));
    REQUIRE(selected.GetNumInputs() == reference.GetNumInputs());
    REQUIRE(selected.GetNumOutputs() == reference.GetNumOutputs());
    REQUIRE(selected.GetNumOutputs() > 0);

    for (size_t iteration = 0; iteration < 3; ++iteration) {
        for (size_t index = 0; index < selected.GetNumInputs(); ++index) {
            auto input          = selected.GetInputTensor(index);
            auto referenceInput = reference.GetInputTensor(index);
            REQUIRE(input->Bytes() == referenceInput->Bytes());
            if (input->Type() == fwk::iface::TensorType::FP32) {
                std::fill_n(input->GetData<float>(),
                            input->GetNumElements(),
                            static_cast<float>(iteration) / 4.0f);
            } else {
                std::memset(input->GetData(), static_cast<int>(iteration), input->Bytes());
            }
            std::memcpy(referenceInput->GetData(), input->GetData(), input->Bytes());
        }
        REQUIRE(selected.RunInference());
        REQUIRE(reference.RunInference());
        for (size_t index = 0; index < selected.GetNumOutputs(); ++index) {
            auto output          = selected.GetOutputTensor(index);
            auto referenceOutput = reference.GetOutputTensor(index);
            REQUIRE(output->Bytes() == referenceOutput->Bytes());
            REQUIRE(std::memcmp(output->GetData(), referenceOutput->GetData(), output->Bytes()) ==
                    0);
        }
    }
}
#endif
