/* SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates
 * <open-source-office@arm.com>
 * SPDX-License-Identifier: Apache-2.0
 */
#include "GenericTflmModel.hpp"
#include "SelectedTflmModel.hpp"
#include <cstdio>
#include <cstring>

#if !defined(CMSIS_NN)
#error "This comparison must use the CMSIS-NN specialized implementations"
#endif

namespace arm::app::inference_runner {
extern uint8_t* GetModelPointer();
extern size_t GetModelLen();
} // namespace arm::app::inference_runner

namespace {
using namespace arm::app;
constexpr size_t kArenaSize = 262144;
alignas(16) uint8_t g_selectedArena[kArenaSize] __attribute__((section(".bss.tensor_arena")));
alignas(16) uint8_t g_genericArena[kArenaSize] __attribute__((section(".bss.tensor_arena")));

class SelectedModel : public inference_runner::SelectedTflmModel {
public:
    using SelectedTflmModel::GetOpResolver;
};

class GenericModel : public inference_runner::GenericTflmModel {
public:
    using GenericTflmModel::GetOpResolver;
};

unsigned int CountSpecialized(SelectedModel& selected, GenericModel& generic)
{
    unsigned int count = 0;
    for (auto op : {tflite::BuiltinOperator_CONV_2D,
                    tflite::BuiltinOperator_DEPTHWISE_CONV_2D,
                    tflite::BuiltinOperator_FULLY_CONNECTED,
                    tflite::BuiltinOperator_AVERAGE_POOL_2D,
                    tflite::BuiltinOperator_ADD,
                    tflite::BuiltinOperator_SOFTMAX}) {
        const auto* narrow = selected.GetOpResolver().FindOp(op);
        const auto* wide   = generic.GetOpResolver().FindOp(op);
        if (!narrow && !wide) {
            continue;
        }
        if (!narrow || !wide || narrow->invoke == wide->invoke) {
            return 0;
        }
        ++count;
    }
    return count;
}

void FillInput(int8_t* data, size_t size, unsigned int sample)
{
    uint32_t state = 23 + sample;
    for (size_t i = 0; i < size; ++i) {
        state = state * 1664525U + 1013904223U;
        if (sample == 0) {
            data[i] = 0;
        } else if (sample == 1) {
            data[i] = -128;
        } else if (sample == 2) {
            data[i] = 127;
        } else {
            const uint32_t value = sample == 3 ? (i & 255U) : (state >> 24);
            data[i]              = static_cast<int8_t>(static_cast<int32_t>(value) - 128);
        }
    }
}

bool CompareOutputs()
{
    fwk::iface::MemoryRegion modelMem{inference_runner::GetModelPointer(),
                                      inference_runner::GetModelLen()};
    fwk::iface::MemoryRegion selectedMem{g_selectedArena, kArenaSize};
    fwk::iface::MemoryRegion genericMem{g_genericArena, kArenaSize};
    SelectedModel selected;
    GenericModel generic;
    if (!selected.Init(selectedMem, modelMem) || !generic.Init(genericMem, modelMem) ||
        selected.GetNumInputs() != 1 || generic.GetNumInputs() != 1 ||
        selected.GetNumOutputs() != 1 || generic.GetNumOutputs() != 1) {
        return false;
    }
    const auto count = CountSpecialized(selected, generic);
    if (count == 0) {
        return false;
    }
    auto input           = selected.GetInputTensor(0);
    auto referenceInput  = generic.GetInputTensor(0);
    auto output          = selected.GetOutputTensor(0);
    auto referenceOutput = generic.GetOutputTensor(0);
    if (input->Type() != fwk::iface::TensorType::INT8 ||
        input->Bytes() != referenceInput->Bytes() || output->Bytes() != referenceOutput->Bytes()) {
        return false;
    }
    for (unsigned int sample = 0; sample < 8; ++sample) {
        FillInput(input->GetData<int8_t>(), input->Bytes(), sample);
        std::memcpy(referenceInput->GetData(), input->GetData(), input->Bytes());
        if (!selected.RunInference() || !generic.RunInference() ||
            std::memcmp(output->GetData(), referenceOutput->GetData(), output->Bytes()) != 0) {
            return false;
        }
        uint32_t hash = 2166136261U;
        for (size_t i = 0; i < output->Bytes(); ++i) {
            hash = (hash ^ output->GetData<uint8_t>()[i]) * 16777619U;
        }
        std::printf("INT8_COMPARE sample=%u status=PASS output_fnv1a=%08lx\n",
                    sample,
                    static_cast<unsigned long>(hash));
    }
    std::printf("INT8_COMPARE summary samples=8 operators=%u status=PASS\n", count);
    return true;
}
} // namespace

int main()
{
    const bool passed = CompareOutputs();
    if (!passed) {
        std::puts("INT8_COMPARE status=FAIL");
    }
    return passed ? 0 : 1;
}
