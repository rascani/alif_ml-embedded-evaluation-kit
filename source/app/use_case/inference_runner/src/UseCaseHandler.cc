/*
 * SPDX-FileCopyrightText: Copyright 2021, 2025-2026 Arm Limited and/or its affiliates
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
#include "UseCaseHandler.hpp"

#if defined(INFERENCE_RUNNER_BENCHMARK)
#include "EtMemoryReport.hpp"
#include "InferenceBenchmark.hpp"
#endif

#include "UseCaseCommonUtils.hpp"
#include "hal.h"
#include "mlek/fwk/iface/Model.hpp"
#include "mlek/log/log_macros.h"

#include <cstdlib>
#include <cstring>

namespace arm {
namespace app {

#if !defined(INFERENCE_RUNNER_BENCHMARK)
    static void PopulateInputTensor(const fwk::iface::Model& model)
    {
        const size_t numInputs = model.GetNumInputs();

#if defined(DYNAMIC_IFM_BASE) && defined(DYNAMIC_IFM_SIZE)
        size_t curInputIdx = 0;
#endif /* defined(DYNAMIC_IFM_BASE) && defined(DYNAMIC_IFM_SIZE) */

        /* Populate each input tensor with random data. */
        for (size_t inputIndex = 0; inputIndex < numInputs; inputIndex++) {

            auto inputTensor = model.GetInputTensor(inputIndex);

            debug("Populating input tensor %zu@%p\n", inputIndex, inputTensor->GetData());
            debug("Total input size to be populated: %zu\n", inputTensor->Bytes());

            if (inputTensor->Bytes() > 0) {

                uint8_t* tData = inputTensor->GetData<uint8_t>();

#if defined(DYNAMIC_IFM_BASE) && defined(DYNAMIC_IFM_SIZE)
                if (curInputIdx + inputTensor->Bytes() > DYNAMIC_IFM_SIZE) {
                    printf_err("IFM reserved buffer size insufficient\n");
                    return;
                }
                memcpy(tData,
                       reinterpret_cast<void*>(DYNAMIC_IFM_BASE + curInputIdx),
                       inputTensor->Bytes());
                curInputIdx += inputTensor->Bytes();
#else  /* defined(DYNAMIC_IFM_BASE) */
                /* Random bit patterns can be NaNs for floating-point tensors. */
                if (inputTensor->Type() == fwk::iface::TensorType::FP32) {
                    float* floatData = inputTensor->GetData<float>();
                    for (size_t j = 0; j < inputTensor->GetNumElements(); ++j) {
                        floatData[j] = static_cast<float>(std::rand()) / RAND_MAX;
                    }
                } else if (inputTensor->Type() == fwk::iface::TensorType::FP16) {
                    std::memset(tData, 0, inputTensor->Bytes());
                } else {
                    for (size_t j = 0; j < inputTensor->Bytes(); ++j) {
                        tData[j] = static_cast<uint8_t>(std::rand() & 0xFF);
                    }
                }
#endif /* defined(DYNAMIC_IFM_BASE) && defined(DYNAMIC_IFM_SIZE) */
            }
        }

#if defined(DYNAMIC_IFM_BASE)
        info("%d input tensor/s populated with %d bytes with data read from 0x%08x\n",
             numInputs,
             curInputIdx,
             DYNAMIC_IFM_BASE);
#endif /* defined(DYNAMIC_IFM_BASE) */
    }

#if defined(DYNAMIC_OFM_BASE) && defined(DYNAMIC_OFM_SIZE)
    static void PopulateDynamicOfm(const fwk::iface::Model& model)
    {
        /* Dump the output to a known memory location */
        const size_t numOutputs = model.GetNumOutputs();
        size_t curCopyIdx       = 0;
        auto* const dstPtr      = reinterpret_cast<uint8_t*>(DYNAMIC_OFM_BASE);

        for (size_t outputIdx = 0; outputIdx < numOutputs; ++outputIdx) {
            auto outputTensor = model.GetOutputTensor(outputIdx);
            auto* const tData = outputTensor->GetData<uint8_t>();

            if (tData && outputTensor->Bytes() > 0) {
                if (curCopyIdx + outputTensor->Bytes() > DYNAMIC_OFM_SIZE) {
                    printf_err("OFM reserved buffer size insufficient\n");
                    return;
                }
                memcpy(dstPtr + curCopyIdx, tData, outputTensor->Bytes());
                curCopyIdx += outputTensor->Bytes();
            }
        }

        info("%d output tensor/s worth %d bytes copied to 0x%08x\n",
             numOutputs,
             curCopyIdx,
             DYNAMIC_OFM_BASE);
    }
#endif /* defined (DYNAMIC_OFM_BASE) && defined(DYNAMIC_OFM_SIZE) */

#if VERIFY_TEST_OUTPUT
    static void DumpInputs(const fwk::iface::Model& model, const char* message)
    {
        info("%s\n", message);
        for (size_t inputIndex = 0; inputIndex < model.GetNumInputs(); inputIndex++) {
            arm::app::DumpTensor(model.GetInputTensor(inputIndex));
        }
    }

    static void DumpOutputs(const fwk::iface::Model& model, const char* message)
    {
        info("%s\n", message);
        for (size_t outputIndex = 0; outputIndex < model.GetNumOutputs(); outputIndex++) {
            arm::app::DumpTensor(model.GetOutputTensor(outputIndex));
        }
    }
#endif /* VERIFY_TEST_OUTPUT */

#endif /* !INFERENCE_RUNNER_BENCHMARK */

    bool RunInferenceHandler(ApplicationContext& ctx)
    {
        auto& model = ctx.Get<fwk::iface::Model&>("model");

#if defined(INFERENCE_RUNNER_BENCHMARK)
        inference_runner::BenchmarkResult result;
        if (!inference_runner::RunBenchmark(
                model, INFERENCE_RUNNER_WARMUP_COUNT, INFERENCE_RUNNER_ITERATION_COUNT, result)) {
            return false;
        }
#if defined(ET_MEMORY_REPORT)
        const size_t heapBeforeReport = inference_runner::EtAllocatedHeapBytes();
#endif
        inference_runner::PrintBenchmark(result);
#if defined(ET_MEMORY_REPORT)
        const size_t heapAfterReport = inference_runner::EtAllocatedHeapBytes();
        info("MEMORY et_invoke heap_before=%zu heap_after=%zu scope=inference_batch_v1\n",
             result.heapBeforeInference,
             result.heapAfterInference);
        info("MEMORY et_diagnostics heap_before=%zu heap_after=%zu\n",
             heapBeforeReport,
             heapAfterReport);
#endif
        return true;
#else
        auto& profiler = ctx.Get<Profiler&>("profiler");

        constexpr uint32_t dataPsnTxtInfStartX = 150;
        constexpr uint32_t dataPsnTxtInfStartY = 40;

        if (!model.IsInited()) {
            printf_err("Model is not initialised! Terminating processing.\n");
            return false;
        }

#if VERIFY_TEST_OUTPUT
        DumpInputs(model, "Initial input tensors values");
        DumpOutputs(model, "Initial output tensors values");
#endif /* VERIFY_TEST_OUTPUT */

        PopulateInputTensor(model);

#if VERIFY_TEST_OUTPUT
        DumpInputs(model, "input tensors populated");
#endif /* VERIFY_TEST_OUTPUT */

        /* Strings for presentation/logging. */
        std::string str_inf{"Running inference... "};

        /* Display message on the LCD - inference running. */
        hal_display_show_text(
            str_inf.c_str(), str_inf.size(), dataPsnTxtInfStartX, dataPsnTxtInfStartY, 0);

        if (!RunInference(model, profiler)) {
            return false;
        }

        /* Erase. */
        str_inf = std::string(str_inf.size(), ' ');
        hal_display_show_text(
            str_inf.c_str(), str_inf.size(), dataPsnTxtInfStartX, dataPsnTxtInfStartY, 0);

        info("Final results:\n");
        info("Total number of inferences: 1\n");
        profiler.PrintProfilingResult();

#if VERIFY_TEST_OUTPUT
        DumpOutputs(model, "output tensors post inference");
#endif /* VERIFY_TEST_OUTPUT */

#if defined(DYNAMIC_OFM_BASE) && defined(DYNAMIC_OFM_SIZE)
        PopulateDynamicOfm(model);
#endif /* defined (DYNAMIC_OFM_BASE) && defined(DYNAMIC_OFM_SIZE) */

        return true;
#endif /* INFERENCE_RUNNER_BENCHMARK */
    }

} /* namespace app */
} /* namespace arm */
