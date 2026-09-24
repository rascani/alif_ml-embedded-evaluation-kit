/*
 * SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates
 * <open-source-office@arm.com>
 * SPDX-License-Identifier: Apache-2.0
 */
#include "InferenceRunnerModel.hpp"
#include "TflmMemoryAudit.hpp"

#include <catch.hpp>
#include <cstring>

namespace arm::app::inference_runner {
extern uint8_t* GetModelPointer();
extern size_t GetModelLen();
} // namespace arm::app::inference_runner

using namespace arm::app::inference_runner;

TEST_CASE("Audited arena preserves ordinary TFLM allocation layout and outputs", "[memory]")
{
    alignas(16) static uint8_t plain[ACTIVATION_BUF_SZ];
    alignas(16) static uint8_t tracked[ACTIVATION_BUF_SZ];
    arm::app::fwk::iface::MemoryRegion plainMem{plain, sizeof(plain)};
    arm::app::fwk::iface::MemoryRegion trackedMem{tracked, sizeof(tracked)};
    arm::app::fwk::iface::MemoryRegion modelMem{GetModelPointer(), GetModelLen()};
    TflmInferenceModel reference;
    TflmInferenceModel audited;
    auto* arena = TrackedArenaAllocator::Create(tracked, sizeof(tracked));
    REQUIRE(arena);
    arm::app::fwk::tflm::TflmBackendData backend;
    backend.m_pAllocator = CreateAuditedMicroAllocator(*arena);
    REQUIRE(backend.m_pAllocator);
    REQUIRE(reference.Init(plainMem, modelMem));
    REQUIRE(audited.Init(trackedMem, modelMem, &backend));
    REQUIRE(arena->GetUsedBytes() - arena->TrackingOverhead() ==
            reference.GetBackendData().m_pInterpreter->arena_used_bytes());
    REQUIRE(arena->PeakBytes() >= arena->GetUsedBytes());
    arena->BeginInference();
    for (size_t iteration = 0; iteration < 3; ++iteration) {
        for (size_t i = 0; i < reference.GetNumInputs(); ++i) {
            auto input = reference.GetInputTensor(i);
            auto other = audited.GetInputTensor(i);
            std::memset(input->GetData(), static_cast<int>(iteration), input->Bytes());
            std::memcpy(other->GetData(), input->GetData(), input->Bytes());
        }
        REQUIRE(reference.RunInference());
        REQUIRE(audited.RunInference());
        for (size_t i = 0; i < reference.GetNumOutputs(); ++i) {
            auto output = reference.GetOutputTensor(i);
            auto other  = audited.GetOutputTensor(i);
            REQUIRE(output->Bytes() == other->Bytes());
            REQUIRE(std::memcmp(output->GetData(), other->GetData(), output->Bytes()) == 0);
        }
    }
    REQUIRE(arena->InferenceAllocationCalls() == 0);
}

TEST_CASE("Arena peak includes released initialization temporaries without double counting tail",
          "[memory]")
{
    alignas(16) uint8_t storage[4096];
    auto* arena = TrackedArenaAllocator::Create(storage, sizeof(storage));
    REQUIRE(arena);
    const size_t initialTail = arena->GetPersistentUsedBytes();
    REQUIRE(arena->AllocatePersistentBuffer(128, 16));
    const size_t tail = arena->GetPersistentUsedBytes();
    REQUIRE(tail >= initialTail + 128);
    auto* temporary = arena->AllocateTemp(1024, 16);
    REQUIRE(temporary);
    REQUIRE(arena->PeakBytes() == tail + 1024);
    arena->DeallocateTemp(temporary);
    REQUIRE(arena->ResetTempAllocations() == kTfLiteOk);
    REQUIRE(arena->GetUsedBytes() == tail);
    REQUIRE(arena->ReserveNonPersistentOverlayMemory(256, 16) == kTfLiteOk);
    arena->BeginInference();
    REQUIRE(arena->InferencePeakBytes() == tail + 256);
    REQUIRE(arena->InitPeakBytes() == tail + 1024);
}
