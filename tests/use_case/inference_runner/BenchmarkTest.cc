/*
 * SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates
 * <open-source-office@arm.com>
 * SPDX-License-Identifier: Apache-2.0
 */
#include "InferenceBenchmark.hpp"
#if defined(MLEK_FWK_TFLM)
#include "InferenceRunnerModel.hpp"
using TestModel = arm::app::inference_runner::TflmInferenceModel;
#else
#include "mlek/fwk/executorch/EtModel.hpp"
using TestModel = arm::app::fwk::et::EtModel;
#endif

#include <catch.hpp>
#include <cstring>
#include <numeric>

namespace arm::app::inference_runner {
extern uint8_t* GetModelPointer();
extern size_t GetModelLen();
} // namespace arm::app::inference_runner

using namespace arm::app::inference_runner;

TEST_CASE("Benchmark statistics handle odd, even, and large values and preserve sample order",
          "[benchmark]")
{
    BenchmarkStatistics statistics;
    REQUIRE_FALSE(SummarizeBenchmark({}, statistics));
    REQUIRE(SummarizeBenchmark({17}, statistics));
    REQUIRE(statistics.minimum == 17);
    REQUIRE(statistics.median == 17);
    REQUIRE(statistics.p95 == 17);
    REQUIRE(SummarizeBenchmark({9, 1, 5}, statistics));
    REQUIRE(statistics.median == 5);
    REQUIRE(statistics.p95 == 9);

    std::vector<uint64_t> samples(100);
    std::iota(samples.rbegin(), samples.rend(), uint64_t{1});
    const auto original = samples;
    REQUIRE(SummarizeBenchmark(samples, statistics));
    REQUIRE(samples == original);
    REQUIRE(statistics.minimum == 1);
    REQUIRE(statistics.mean == Approx(50.5));
    REQUIRE(statistics.median == Approx(50.5));
    REQUIRE(statistics.maximum == 100);
    REQUIRE(statistics.p95 == 95);

    const uint64_t large = uint64_t{1} << 40;
    REQUIRE(SummarizeBenchmark({large + 8, large + 2}, statistics));
    REQUIRE(statistics.minimum == large + 2);
    REQUIRE(statistics.mean == Approx(static_cast<double>(large + 5)));
    REQUIRE(statistics.median == Approx(static_cast<double>(large + 5)));
}

TEST_CASE("Benchmark rejects missing, changed, and backward counters", "[benchmark]")
{
    pmu_counters start{};
    pmu_counters end{};
    uint64_t elapsed{};
    const char* name{};
    const char* unit{};
    REQUIRE_FALSE(GetBenchmarkElapsed(start, end, elapsed, name, unit));
    start.initialised = end.initialised = true;
    start.num_counters = end.num_counters = 1;
    start.counters[0]                     = {uint64_t{1} << 40, "CPU TOTAL", "cycles"};
    end.counters[0]                       = start.counters[0];
    end.counters[0].value += 123;
    REQUIRE(GetBenchmarkElapsed(start, end, elapsed, name, unit));
    REQUIRE(elapsed == 123);
    end.counters[0].value = start.counters[0].value - 1;
    REQUIRE_FALSE(GetBenchmarkElapsed(start, end, elapsed, name, unit));
    end.counters[0]      = start.counters[0];
    end.counters[0].unit = "microseconds";
    REQUIRE_FALSE(GetBenchmarkElapsed(start, end, elapsed, name, unit));
    start.counters[0] = {0, "Duration", "microseconds"};
    end.counters[0]   = start.counters[0];
    REQUIRE(GetBenchmarkElapsed(start, end, elapsed, name, unit));
    REQUIRE(elapsed == 0); // Native timer resolution can exceed a tiny model's duration.
    end.num_counters = 0;
    REQUIRE_FALSE(GetBenchmarkElapsed(start, end, elapsed, name, unit));
}

class CountingModel : public TestModel {
public:
    size_t calls{};
    size_t failAt{};
    std::vector<std::vector<uint8_t>> firstInputs;

    bool RunInference() override
    {
        ++calls;
        for (size_t index = 0; index < this->GetNumInputs(); ++index) {
            auto tensor = this->GetInputTensor(index);
            auto* data  = tensor->template GetData<uint8_t>();
            std::vector<uint8_t> input(data, data + tensor->Bytes());
            if (calls == 1) {
                firstInputs.push_back(input);
                if (tensor->GetNumElements() > 0) {
                    if (tensor->Type() == arm::app::fwk::iface::TensorType::FP32) {
                        REQUIRE(tensor->template GetData<float>()[0] ==
                                static_cast<float>(static_cast<int>((index * 13) % 17) - 8) / 8.0f);
                    } else {
                        REQUIRE(data[0] == static_cast<uint8_t>(index * 13 + 11));
                    }
                }
            } else {
                REQUIRE(input == firstInputs[index]);
            }
        }
        if (calls == failAt) {
            return false;
        }
        const bool success = TestModel::RunInference();
        for (size_t index = 0; index < this->GetNumInputs(); ++index) {
            auto tensor = this->GetInputTensor(index);
            std::memset(tensor->GetData(), 0xA5, tensor->Bytes());
        }
        return success;
    }
};

TEST_CASE("Benchmark invokes the real model 111 times and restores input before each invocation",
          "[benchmark]")
{
    alignas(16) static uint8_t arena[ACTIVATION_BUF_SZ];
    arm::app::fwk::iface::MemoryRegion computeMem{arena, sizeof(arena)};
    arm::app::fwk::iface::MemoryRegion modelMem{GetModelPointer(), GetModelLen()};
    CountingModel model;
    BenchmarkResult result;
    REQUIRE_FALSE(RunBenchmark(model, 10, 100, result));
    REQUIRE(model.Init(computeMem, modelMem));
    REQUIRE_FALSE(RunBenchmark(model, 10, 0, result));
    REQUIRE_FALSE(RunBenchmark(model, 10, 1001, result));
    REQUIRE_FALSE(RunBenchmark(model, 1001, 100, result));
    REQUIRE(model.calls == 0);

    SECTION("Complete run")
    {
        REQUIRE(RunBenchmark(model, 10, 100, result));
        REQUIRE(model.calls == 111);
        REQUIRE(result.samples.size() == 100);
        REQUIRE(result.warmups == 10);
        REQUIRE(std::string(result.unit) == "microseconds");
    }
    SECTION("No warm-ups and one measurement")
    {
        REQUIRE(RunBenchmark(model, 0, 1, result));
        REQUIRE(model.calls == 2);
        REQUIRE(result.samples.size() == 1);
        REQUIRE(result.statistics.minimum == result.samples.front());
    }
    SECTION("Stop on first-inference failure")
    {
        model.failAt = 1;
        REQUIRE_FALSE(RunBenchmark(model, 10, 100, result));
        REQUIRE(model.calls == 1);
    }
    SECTION("Stop on warm-up failure")
    {
        model.failAt = 2;
        REQUIRE_FALSE(RunBenchmark(model, 10, 100, result));
        REQUIRE(model.calls == 2);
    }
    SECTION("Stop on measured-inference failure")
    {
        model.failAt = 12;
        REQUIRE_FALSE(RunBenchmark(model, 10, 100, result));
        REQUIRE(model.calls == 12);
    }
}
