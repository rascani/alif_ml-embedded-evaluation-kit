/*
 * SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates
 * <open-source-office@arm.com>
 * SPDX-License-Identifier: Apache-2.0
 */
#include "InferenceBenchmark.hpp"
#include "EtMemoryReport.hpp"

#include "mlek/log/log_macros.h"

#include <algorithm>
#include <cinttypes>
#include <cstring>
#include <numeric>

namespace arm::app::inference_runner {

bool SummarizeBenchmark(const std::vector<uint64_t>& samples, BenchmarkStatistics& statistics)
{
    if (samples.empty()) {
        return false;
    }
    auto sorted = samples;
    std::sort(sorted.begin(), sorted.end());
    const size_t count = sorted.size();
    statistics.minimum = sorted.front();
    statistics.maximum = sorted.back();
    statistics.mean    = std::accumulate(sorted.begin(), sorted.end(), 0.0) / count;
    statistics.median  = static_cast<double>(sorted[count / 2]);
    if (count % 2 == 0) {
        statistics.median = static_cast<double>(sorted[count / 2 - 1]) / 2.0 +
                            static_cast<double>(sorted[count / 2]) / 2.0;
    }
    statistics.p95 = sorted[count - count / 20 - 1];
    return true;
}

bool GetBenchmarkElapsed(const pmu_counters& start,
                         const pmu_counters& end,
                         uint64_t& elapsed,
                         const char*& counterName,
                         const char*& unit)
{
    if (!start.initialised || !end.initialised || start.num_counters == 0 ||
        start.num_counters > NUM_PMU_COUNTERS || start.num_counters != end.num_counters) {
        return false;
    }
    for (size_t index = 0; index < start.num_counters; ++index) {
        const auto& before = start.counters[index];
        const auto& after  = end.counters[index];
        if (!before.name || !before.unit || !after.name || !after.unit) {
            return false;
        }
        const bool cpuCycles =
            std::strcmp(before.name, "CPU TOTAL") == 0 && std::strcmp(before.unit, "cycles") == 0;
        const bool nativeTime = std::strcmp(before.name, "Duration") == 0 &&
                                std::strcmp(before.unit, "microseconds") == 0;
        if (cpuCycles || nativeTime) {
            if (std::strcmp(before.name, after.name) != 0 ||
                std::strcmp(before.unit, after.unit) != 0 || after.value < before.value) {
                return false;
            }
            elapsed     = after.value - before.value;
            counterName = before.name;
            unit        = before.unit;
            return true;
        }
    }
    return false;
}

static bool PopulateBenchmarkInputs(fwk::iface::Model& model)
{
    for (size_t index = 0; index < model.GetNumInputs(); ++index) {
        auto tensor = model.GetInputTensor(index);
        if (!tensor || (tensor->Bytes() > 0 && !tensor->GetData())) {
            printf_err("Benchmark input %zu has no storage\n", index);
            return false;
        }
        if (tensor->Type() == fwk::iface::TensorType::FP32) {
            auto* data = tensor->GetData<float>();
            for (size_t element = 0; element < tensor->GetNumElements(); ++element) {
                data[element] =
                    static_cast<float>(static_cast<int>((element + index * 13) % 17) - 8) / 8.0f;
            }
        } else if (tensor->Type() == fwk::iface::TensorType::INT8 ||
                   tensor->Type() == fwk::iface::TensorType::UINT8) {
            auto* data = tensor->GetData<uint8_t>();
            for (size_t element = 0; element < tensor->Bytes(); ++element) {
                data[element] = static_cast<uint8_t>(element * 37 + index * 13 + 11);
            }
        } else {
            printf_err("synthetic_v1 supports fp32, int8 and uint8 inputs only\n");
            return false;
        }
    }
    return true;
}

static bool MeasureInference(fwk::iface::Model& model, uint64_t& elapsed, BenchmarkResult& result)
{
    pmu_counters start{};
    pmu_counters end{};
    hal_pmu_init();
    hal_pmu_get_counters(&start);
    const bool success = model.RunInference();
    hal_pmu_get_counters(&end);
    hal_pmu_final();
    if (!success) {
        printf_err("Benchmark inference failed\n");
        return false;
    }
    const char* name{};
    const char* unit{};
    if (!GetBenchmarkElapsed(start, end, elapsed, name, unit) ||
        (result.counterName &&
         (std::strcmp(result.counterName, name) != 0 || std::strcmp(result.unit, unit) != 0))) {
        printf_err("Benchmark requires a valid monotonic CPU counter\n");
        return false;
    }
    result.counterName = name;
    result.unit        = unit;
    return true;
}

bool RunBenchmark(fwk::iface::Model& model,
                  size_t warmups,
                  size_t iterations,
                  BenchmarkResult& result)
{
    result = {};
    if (!model.IsInited() || iterations == 0 || iterations > 1000 || warmups > 1000) {
        printf_err("Benchmark requires an initialized model and valid iteration counts\n");
        return false;
    }
    result.warmups = warmups;
    // Allocate sample storage before the first inference; no container grows during timing.
    result.samples.resize(iterations);
#if defined(ET_MEMORY_REPORT)
    result.heapBeforeInference = EtAllocatedHeapBytes();
#endif
    if (!PopulateBenchmarkInputs(model) || !MeasureInference(model, result.first, result)) {
        return false;
    }
    for (size_t index = 0; index < warmups; ++index) {
        if (!PopulateBenchmarkInputs(model) || !model.RunInference()) {
            printf_err("Benchmark warm-up %zu failed\n", index);
            return false;
        }
    }
    for (size_t index = 0; index < iterations; ++index) {
        if (!PopulateBenchmarkInputs(model) ||
            !MeasureInference(model, result.samples[index], result)) {
            printf_err("Benchmark sample %zu failed\n", index);
            return false;
        }
    }
#if defined(ET_MEMORY_REPORT)
    result.heapAfterInference = EtAllocatedHeapBytes();
#endif
    return SummarizeBenchmark(result.samples, result.statistics);
}

void PrintBenchmark(const BenchmarkResult& result)
{
    const auto& stats = result.statistics;
    info("Final results:\n");
    info("Total number of inferences: %zu\n", 1 + result.warmups + result.samples.size());
    info("BENCHMARK config version=1 input=synthetic_v1 warmups=%zu measured=%zu\n",
         result.warmups,
         result.samples.size());
    info("BENCHMARK first value=%" PRIu64 " unit=%s\n", result.first, result.unit);
    for (size_t index = 0; index < result.samples.size(); ++index) {
        info("BENCHMARK sample index=%zu value=%" PRIu64 " unit=%s\n",
             index,
             result.samples[index],
             result.unit);
    }
    info("BENCHMARK summary count=%zu min=%" PRIu64 " mean=%.3f median=%.3f max=%" PRIu64
         " p95=%" PRIu64 " unit=%s\n",
         result.samples.size(),
         stats.minimum,
         stats.mean,
         stats.median,
         stats.maximum,
         stats.p95,
         result.unit);
}

} // namespace arm::app::inference_runner
