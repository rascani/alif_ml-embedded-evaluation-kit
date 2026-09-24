/*
 * SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates
 * <open-source-office@arm.com>
 * SPDX-License-Identifier: Apache-2.0
 */
#include "TflmMemoryAudit.hpp"

#if defined(MLEK_FWK_TFLM)
#include "mlek/log/log_macros.h"
#include "tensorflow/lite/micro/memory_planner/greedy_memory_planner.h"

#include <algorithm>
#include <malloc.h>
#include <new>

namespace arm::app::inference_runner {

TrackedArenaAllocator::TrackedArenaAllocator(uint8_t* buffer, size_t bytes) :
    SingleArenaBufferAllocator(buffer, bytes)
{}

TrackedArenaAllocator* TrackedArenaAllocator::Create(uint8_t* buffer, size_t bytes)
{
    TrackedArenaAllocator temporary(buffer, bytes);
    auto* storage = temporary.AllocatePersistentBuffer(
        sizeof(SingleArenaBufferAllocator) + TrackingOverhead(), alignof(TrackedArenaAllocator));
    return storage ? new (storage) TrackedArenaAllocator(temporary) : nullptr;
}

void TrackedArenaAllocator::Observe()
{
    const size_t used = this->GetUsedBytes();
    this->m_peak      = std::max(this->m_peak, used);
    if (this->m_inference) {
        this->m_inferencePeak = std::max(this->m_inferencePeak, used);
        ++this->m_inferenceAllocationCalls;
    } else {
        this->m_initPeak = std::max(this->m_initPeak, used);
    }
}

uint8_t* TrackedArenaAllocator::AllocatePersistentBuffer(size_t bytes, size_t alignment)
{
    auto* result = SingleArenaBufferAllocator::AllocatePersistentBuffer(bytes, alignment);
    this->Observe();
    return result;
}

uint8_t* TrackedArenaAllocator::AllocateTemp(size_t bytes, size_t alignment)
{
    auto* result = SingleArenaBufferAllocator::AllocateTemp(bytes, alignment);
    this->Observe();
    return result;
}

TfLiteStatus TrackedArenaAllocator::ResizeBuffer(uint8_t* buffer, size_t bytes, size_t alignment)
{
    auto status = SingleArenaBufferAllocator::ResizeBuffer(buffer, bytes, alignment);
    this->Observe();
    return status;
}

void TrackedArenaAllocator::BeginInference()
{
    this->m_inference                = true;
    this->m_inferencePeak            = this->GetUsedBytes();
    this->m_inferenceAllocationCalls = 0;
}

size_t TrackedArenaAllocator::PeakBytes() const
{ return this->m_peak; }
size_t TrackedArenaAllocator::InitPeakBytes() const
{ return this->m_initPeak; }
size_t TrackedArenaAllocator::InferencePeakBytes() const
{ return this->m_inferencePeak; }
size_t TrackedArenaAllocator::InferenceAllocationCalls() const
{ return this->m_inferenceAllocationCalls; }
size_t TrackedArenaAllocator::TrackingOverhead()
{
    // Keep subsequent allocations at the same offsets modulo TFLM's 16-byte alignment.
    return (sizeof(TrackedArenaAllocator) - sizeof(SingleArenaBufferAllocator) + 15) / 16 * 16;
}

tflite::MicroAllocator* CreateAuditedMicroAllocator(TrackedArenaAllocator& arena)
{
    auto* storage = arena.AllocatePersistentBuffer(sizeof(tflite::GreedyMemoryPlanner),
                                                   alignof(tflite::GreedyMemoryPlanner));
    if (!storage) {
        return nullptr;
    }
    auto* planner = ::new (storage) tflite::GreedyMemoryPlanner();
    return tflite::MicroAllocator::Create(&arena, planner);
}

size_t AllocatedHeapBytes()
{
#if defined(__GLIBC__)
    return mallinfo2().uordblks;
#else
    return static_cast<size_t>(mallinfo().uordblks);
#endif
}

void PrintTflmMemory(const TrackedArenaAllocator& arena,
                     size_t reservedBytes,
                     size_t modelObjectBytes,
                     size_t heapBeforeInit,
                     size_t heapAfterInit)
{
    if (heapAfterInit < heapBeforeInit) {
        printf_err("MEMORY invalid model initialization heap delta\n");
        return;
    }
    const size_t overhead  = arena.TrackingOverhead();
    const size_t heapDelta = heapAfterInit - heapBeforeInit;
    const size_t outside   = modelObjectBytes + heapDelta;
    info("MEMORY arena reserved=%zu head=%zu persistent=%zu init_peak=%zu invoke_peak=%zu "
         "peak=%zu audit_overhead=%zu raw_peak=%zu invoke_allocation_calls=%zu\n",
         reservedBytes,
         arena.GetNonPersistentUsedBytes(),
         arena.GetPersistentUsedBytes() - overhead,
         arena.InitPeakBytes() - overhead,
         arena.InferencePeakBytes() - overhead,
         arena.PeakBytes() - overhead,
         overhead,
         arena.PeakBytes(),
         arena.InferenceAllocationCalls());
    info("MEMORY outside model_object=%zu init_heap_delta=%zu interpreter_object=%zu "
         "persistent=%zu\n",
         modelObjectBytes,
         heapDelta,
         sizeof(tflite::MicroInterpreter),
         outside);
    info("MEMORY total inference_peak=%zu lifecycle_arena_plus_persistent=%zu\n",
         arena.InferencePeakBytes() - overhead + outside,
         arena.PeakBytes() - overhead + outside);
}

} // namespace arm::app::inference_runner
#endif
