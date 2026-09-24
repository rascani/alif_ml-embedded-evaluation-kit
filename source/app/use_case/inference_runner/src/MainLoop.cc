/*
 * SPDX-FileCopyrightText: Copyright 2021, 2024-2026 Arm Limited and/or its
 * affiliates <open-source-office@arm.com>
 * SPDX-License-Identifier: Apache-2.0
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
#include "hal.h" /* Brings in platform definitions. */
#if defined(MLEK_FWK_TFLM)
#include "InferenceRunnerModel.hpp"
#if defined(TFLM_MEMORY_AUDIT)
#include "TflmMemoryAudit.hpp"
#endif
#elif defined(MLEK_FWK_EXECUTORCH)
#include "EtMemoryReport.hpp"
#include "mlek/fwk/executorch/EtModel.hpp"
#endif
#if defined(INFERENCE_VALIDATION)
#include "InferenceValidation.hpp"
#endif
#include "BufAttributes.hpp"      /* Buffer attributes to be applied */
#include "UseCaseCommonUtils.hpp" /* Utils functions. */
#include "UseCaseHandler.hpp"     /* Handlers for different user options. */
#include "mlek/log/log_macros.h"  /* Logging functions */

namespace arm {
namespace app {
    static uint8_t activationBuf[ACTIVATION_BUF_SZ] ACTIVATION_BUF_ATTRIBUTE;
    namespace inference_runner {
#if defined(DYNAMIC_MODEL_BASE) && defined(DYNAMIC_MODEL_SIZE)

        static uint8_t* GetModelPointer()
        {
            info("Model pointer: 0x%08x\n", DYNAMIC_MODEL_BASE);
            return reinterpret_cast<uint8_t*>(DYNAMIC_MODEL_BASE);
        }

        static size_t GetModelLen()
        {
            /* TODO: Can we get the actual model size here somehow?
             * Currently we return the reserved space. It is possible to do
             * so by reading the memory pattern but it will not be reliable. */
            return static_cast<size_t>(DYNAMIC_MODEL_SIZE);
        }

#else /* defined(DYNAMIC_MODEL_BASE) && defined(DYNAMIC_MODEL_SIZE) */

        extern uint8_t* GetModelPointer();
        extern size_t GetModelLen();

#endif /* defined(DYNAMIC_MODEL_BASE) && defined(DYNAMIC_MODEL_SIZE) */
    } /* namespace inference_runner */
} /* namespace app */
} /* namespace arm */

void MainLoop()
{
#if defined(BENCHMARK_BUILD_ID)
    info("BENCHMARK build id=%s\n", BENCHMARK_BUILD_ID);
#endif
#if defined(MLEK_FWK_TFLM)
    arm::app::inference_runner::TflmInferenceModel model;
#elif defined(MLEK_FWK_EXECUTORCH)
    arm::app::fwk::et::EtModel model;
#endif
    arm::app::fwk::iface::MemoryRegion modelMem{arm::app::inference_runner::GetModelPointer(),
                                                arm::app::inference_runner::GetModelLen()};
    arm::app::fwk::iface::MemoryRegion computeMem{arm::app::activationBuf,
                                                  sizeof(arm::app::activationBuf)};

#if defined(TFLM_MEMORY_AUDIT)
    auto* arena =
        arm::app::inference_runner::TrackedArenaAllocator::Create(computeMem.data, computeMem.size);
    arm::app::fwk::tflm::TflmBackendData backend;
    if (!arena ||
        !(backend.m_pAllocator = arm::app::inference_runner::CreateAuditedMicroAllocator(*arena))) {
        printf_err("Failed to initialise audited allocator\n");
        return;
    }
    const size_t heapBeforeInit = arm::app::inference_runner::AllocatedHeapBytes();
    const bool initialized      = model.Init(computeMem, modelMem, &backend);
    const size_t heapAfterInit  = arm::app::inference_runner::AllocatedHeapBytes();
#elif defined(ET_MEMORY_REPORT)
    arm::app::fwk::et::EtBackendData backend;
    backend.m_methodName        = "forward";
    const size_t heapBeforeInit = arm::app::inference_runner::EtAllocatedHeapBytes();
    const bool initialized      = model.Init(computeMem, modelMem, &backend);
    const size_t heapAfterInit  = arm::app::inference_runner::EtAllocatedHeapBytes();
#else
    const bool initialized = model.Init(computeMem, modelMem);
#endif
    if (!initialized) {
        printf_err("Failed to initialise model\n");
        return;
    }

    /* Instantiate application context. */
    arm::app::ApplicationContext caseContext;

    arm::app::Profiler profiler{"inference_runner"};
    caseContext.Set<arm::app::Profiler&>("profiler", profiler);
    caseContext.Set<arm::app::fwk::iface::Model&>("model", model);

#if defined(TFLM_MEMORY_AUDIT) || defined(ET_MEMORY_REPORT)
    info("BENCHMARK model id=%s sha256=%s bytes=%zu\n",
         BENCHMARK_MODEL_ID,
         BENCHMARK_MODEL_SHA256,
         modelMem.size);
#endif
#if defined(TFLM_MEMORY_AUDIT)
    arena->BeginInference();
#endif
#if defined(ET_MEMORY_REPORT)
    const auto& etBackend = model.GetBackendData();
    info("MEMORY et_init method_peak=%zu temp_peak=%zu\n",
         etBackend.m_methodAllocPtr->UsedSizePeak(),
         etBackend.m_tmpAllocPtr->UsedSizePeak());
    etBackend.m_methodAllocPtr->ResetPeak();
    etBackend.m_tmpAllocPtr->ResetPeak();
#endif

    /* Loop. */
    if (RunInferenceHandler(caseContext)) {
#if defined(TFLM_MEMORY_AUDIT)
        arm::app::inference_runner::PrintTflmMemory(
            *arena, computeMem.size, sizeof(model), heapBeforeInit, heapAfterInit);
#endif
#if defined(ET_MEMORY_REPORT)
        if (!arm::app::inference_runner::PrintEtMemory(model, heapBeforeInit, heapAfterInit)) {
            return;
        }
#endif
#if defined(INFERENCE_VALIDATION)
        if (!arm::app::inference_runner::ValidateInference(model)) {
            printf_err("Validation failed.\n");
            return;
        }
#endif
        info("Inference completed.\n");
    } else {
        printf_err("Inference failed.\n");
    }
}
