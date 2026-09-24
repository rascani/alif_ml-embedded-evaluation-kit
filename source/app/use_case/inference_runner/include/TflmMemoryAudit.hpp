/*
 * SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates
 * <open-source-office@arm.com>
 * SPDX-License-Identifier: Apache-2.0
 */
#ifndef TFLM_MEMORY_AUDIT_HPP
#define TFLM_MEMORY_AUDIT_HPP

#if defined(MLEK_FWK_TFLM)
#include "mlek/fwk/tflm/TflmModel.hpp"
#include "tensorflow/lite/micro/arena_allocator/single_arena_buffer_allocator.h"

namespace arm::app::inference_runner {

/** Track arena high-water marks, including temporary initialization allocations. */
class TrackedArenaAllocator : public tflite::SingleArenaBufferAllocator {
public:
    static TrackedArenaAllocator* Create(uint8_t* buffer, size_t bytes);
    uint8_t* AllocatePersistentBuffer(size_t bytes, size_t alignment) override;
    uint8_t* AllocateTemp(size_t bytes, size_t alignment) override;
    TfLiteStatus ResizeBuffer(uint8_t* buffer, size_t bytes, size_t alignment) override;
    void BeginInference();
    size_t PeakBytes() const;
    size_t InitPeakBytes() const;
    size_t InferencePeakBytes() const;
    size_t InferenceAllocationCalls() const;
    static size_t TrackingOverhead();

private:
    TrackedArenaAllocator(uint8_t* buffer, size_t bytes);
    void Observe();
    size_t m_peak{};
    size_t m_initPeak{};
    size_t m_inferencePeak{};
    size_t m_inferenceAllocationCalls{};
    bool m_inference{};
};

/** Create the normal greedy MicroAllocator using an audited arena. */
tflite::MicroAllocator* CreateAuditedMicroAllocator(TrackedArenaAllocator& arena);

/** Current allocated libc heap bytes, including allocator bookkeeping. */
size_t AllocatedHeapBytes();

/** Print arena and outside-arena persistent costs after all timing is complete. */
void PrintTflmMemory(const TrackedArenaAllocator& arena,
                     size_t reservedBytes,
                     size_t modelObjectBytes,
                     size_t heapBeforeInit,
                     size_t heapAfterInit);

} // namespace arm::app::inference_runner
#endif
#endif
