/*
 * SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates
 * <open-source-office@arm.com>
 * SPDX-License-Identifier: Apache-2.0
 */
#include "EtMemoryReport.hpp"
#if defined(ET_MEMORY_REPORT)
#include "mlek/log/log_macros.h"
#include <malloc.h>

namespace arm::app::inference_runner {
size_t EtAllocatedHeapBytes()
{
#if defined(__GLIBC__)
    return mallinfo2().uordblks;
#else
    return static_cast<size_t>(mallinfo().uordblks);
#endif
}

bool PrintEtMemory(const fwk::et::EtModel& model, size_t heapBeforeInit, size_t heapAfterInit)
{
    const auto& backend = model.GetBackendData();
    const auto& method  = *backend.m_methodAllocPtr;
    const auto& temp    = *backend.m_tmpAllocPtr;
    size_t planned      = 0;
    for (const auto& span : backend.m_plannedSpans) {
        planned += span.size();
    }
    if (heapAfterInit < heapBeforeInit || method.UsedSizeCurrent() < planned ||
        method.UsedSizePeak() != method.UsedSizeCurrent()) {
        printf_err("MEMORY invalid ExecuTorch accounting\n");
        return false;
    }
    const size_t heapDelta = heapAfterInit - heapBeforeInit;
    const size_t outside   = sizeof(model) + heapDelta;
    info("MEMORY et_method reserved=%zu planned=%zu runtime_and_inputs=%zu used=%zu peak=%zu\n",
         static_cast<size_t>(method.size()),
         planned,
         method.UsedSizeCurrent() - planned,
         method.UsedSizeCurrent(),
         method.UsedSizePeak());
    info("MEMORY et_temp reserved=%zu used=%zu peak=%zu\n",
         static_cast<size_t>(temp.size()),
         temp.UsedSizeCurrent(),
         temp.UsedSizePeak());
    info("MEMORY et_outside model_object=%zu init_heap_delta=%zu persistent=%zu\n",
         sizeof(model),
         heapDelta,
         outside);
    info("MEMORY et_total pools_plus_persistent=%zu\n",
         method.UsedSizePeak() + temp.UsedSizePeak() + outside);
    return true;
}
} // namespace arm::app::inference_runner
#endif
