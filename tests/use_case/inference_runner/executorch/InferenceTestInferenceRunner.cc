/*
 * SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates
 * <open-source-office@arm.com>
 * SPDX-License-Identifier: Apache-2.0
 */
#include "mlek/fwk/executorch/EtModel.hpp"

#include <catch.hpp>
#include <cstring>
#include <executorch/schema/program_generated.h>
#include <vector>

namespace arm::app::inference_runner {
extern uint8_t* GetModelPointer();
extern size_t GetModelLen();
} // namespace arm::app::inference_runner

TEST_CASE("ExecuTorch feed-forward model survives repeated invocation and reconstruction",
          "[inference_runner][executorch]")
{
    using namespace arm::app::fwk;
    alignas(16) static uint8_t firstArena[ACTIVATION_BUF_SZ];
    alignas(16) static uint8_t secondArena[ACTIVATION_BUF_SZ];
    iface::MemoryRegion modelMem{arm::app::inference_runner::GetModelPointer(),
                                 arm::app::inference_runner::GetModelLen()};
    std::vector<std::vector<std::vector<uint8_t>>> reference;

    for (auto* arena : {firstArena, secondArena}) {
        if (arena == secondArena) {
            // The first model has been destroyed. Its method and buffers must not be reused.
            std::memset(firstArena, 0xA5, sizeof(firstArena));
        }
        et::EtModel model;
        iface::MemoryRegion computeMem{arena, ACTIVATION_BUF_SZ};
        REQUIRE(model.Init(computeMem, modelMem));
        REQUIRE(model.IsInited());
        REQUIRE(model.GetNumOutputs() > 0);

        for (size_t iteration = 0; iteration < 3; ++iteration) {
            for (size_t index = 0; index < model.GetNumInputs(); ++index) {
                auto input = model.GetInputTensor(index);
                if (input->Type() == iface::TensorType::FP32) {
                    auto* data = input->GetData<float>();
                    for (size_t element = 0; element < input->GetNumElements(); ++element) {
                        data[element] = static_cast<float>(iteration + index + element % 3) / 8;
                    }
                } else {
                    std::memset(input->GetData(), 11 + iteration * 7 + index, input->Bytes());
                }
            }
            REQUIRE(model.RunInference());
            std::vector<std::vector<uint8_t>> outputs;
            for (size_t index = 0; index < model.GetNumOutputs(); ++index) {
                auto output = model.GetOutputTensor(index);
                auto* bytes = output->GetData<uint8_t>();
                outputs.emplace_back(bytes, bytes + output->Bytes());
            }
            if (arena == firstArena) {
                reference.push_back(outputs);
            } else {
                REQUIRE(outputs == reference[iteration]);
            }
        }
    }
}

namespace {
class InputAllocationModel : public arm::app::fwk::et::EtModel {
public:
    size_t inputAllocationBytes{};

protected:
    bool PrepareInputTensors() override
    {
        const auto& allocator = *GetBackendData().m_methodAllocPtr;
        const size_t before   = allocator.UsedSizeCurrent();
        const bool success    = EtModel::PrepareInputTensors();
        inputAllocationBytes  = allocator.UsedSizeCurrent() - before;
        return success;
    }
};
} // namespace

TEST_CASE("ExecuTorch inputs use planned addresses and allocate only unplanned storage",
          "[inference_runner][executorch][inputs]")
{
    using namespace arm::app::fwk;
    alignas(16) static uint8_t arena[ACTIVATION_BUF_SZ];
    iface::MemoryRegion computeMem{arena, sizeof(arena)};
    iface::MemoryRegion modelMem{arm::app::inference_runner::GetModelPointer(),
                                 arm::app::inference_runner::GetModelLen()};
    InputAllocationModel model;
    REQUIRE(model.Init(computeMem, modelMem));
    const auto& backend = model.GetBackendData();
    const auto* program = executorch_flatbuffer::GetProgram(modelMem.data);
    const executorch_flatbuffer::ExecutionPlan* plan = nullptr;
    for (const auto* candidate : *program->execution_plan()) {
        if (candidate->name()->str() == backend.m_methodName) {
            plan = candidate;
            break;
        }
    }
    REQUIRE(plan != nullptr);

    size_t tensorIndex    = 0;
    size_t unplannedBytes = 0;
    for (const auto index : *plan->inputs()) {
        const auto* tensor = plan->values()->Get(index)->val_as_Tensor();
        if (tensor == nullptr) {
            continue;
        }
        auto input = model.GetInputTensor(tensorIndex++);
        REQUIRE(input != nullptr);
        const auto* allocation = tensor->allocation_info();
        if (allocation != nullptr) {
            const uint64_t offset = static_cast<uint64_t>(allocation->memory_offset_high()) << 32 |
                                    allocation->memory_offset_low();
            const auto address    = backend.m_plannedMemAllocPtr->get_offset_address(
                allocation->memory_id() - 1, static_cast<size_t>(offset), input->Bytes());
            REQUIRE(address.ok());
            REQUIRE(input->GetData() == *address);
        } else {
            unplannedBytes += input->Bytes();
            const uintptr_t address = reinterpret_cast<uintptr_t>(input->GetData());
            for (const auto& span : backend.m_plannedSpans) {
                const uintptr_t begin = reinterpret_cast<uintptr_t>(span.data());
                REQUIRE_FALSE((address >= begin && address < begin + span.size()));
            }
        }
    }
    REQUIRE(tensorIndex == model.GetNumInputs());
    if (unplannedBytes == 0) {
        REQUIRE(model.inputAllocationBytes == 0);
    } else {
        REQUIRE(model.inputAllocationBytes >= unplannedBytes);
    }
}
