/*
 * SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates
 * <open-source-office@arm.com>
 * SPDX-License-Identifier: Apache-2.0
 */
#ifndef INFERENCE_BENCHMARK_HPP
#define INFERENCE_BENCHMARK_HPP

#include "hal.h"
#include "mlek/fwk/iface/Model.hpp"

#include <vector>

namespace arm::app::inference_runner {

struct BenchmarkStatistics {
    uint64_t minimum{};
    double mean{};
    double median{};
    uint64_t maximum{};
    uint64_t p95{};
};

struct BenchmarkResult {
    uint64_t first{};
    size_t warmups{};
    const char* counterName{};
    const char* unit{};
    std::vector<uint64_t> samples;
    BenchmarkStatistics statistics;
    // Populated when heap reporting is enabled; keep the public struct layout stable.
    size_t heapBeforeInference{};
    size_t heapAfterInference{};
};

/** Calculate statistics without changing sample order; p95 uses nearest rank. */
bool SummarizeBenchmark(const std::vector<uint64_t>& samples, BenchmarkStatistics& statistics);

/** Extract a monotonic CPU cycle or native duration delta; reject missing/changed counters. */
bool GetBenchmarkElapsed(const pmu_counters& start,
                         const pmu_counters& end,
                         uint64_t& elapsed,
                         const char*& counterName,
                         const char*& unit);

/** Run first, warm-up, and measured invocations with synthetic_v1 input refilled outside timing. */
bool RunBenchmark(fwk::iface::Model& model,
                  size_t warmups,
                  size_t iterations,
                  BenchmarkResult& result);

/** Print all samples and statistics after the complete benchmark has finished. */
void PrintBenchmark(const BenchmarkResult& result);

} // namespace arm::app::inference_runner

#endif
