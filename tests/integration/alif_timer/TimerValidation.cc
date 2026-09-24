/* SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates
 * <open-source-office@arm.com>
 * SPDX-License-Identifier: Apache-2.0
 */
#include "RTE_Components.h"
#include CMSIS_device_header
extern "C" {
#include "hal_pmu.h"
#include "timer_alif.h"
}
#include <cinttypes>
#include <cstdio>
#include <cstring>

#ifndef TIMER_VALIDATION_BUILD_ID
#error "A unique timer-validation build identity is required"
#endif

namespace {
constexpr uint32_t kTolerance   = 32;
constexpr uint32_t kSampleCount = 24;

class DwtClock {
public:
    DwtClock() : m_previous(DWT->CYCCNT), m_value(m_previous) {}
    uint64_t Read()
    {
        const uint32_t current = DWT->CYCCNT;
        m_value += static_cast<uint32_t>(current - m_previous);
        m_wraps += current < m_previous;
        m_previous = current;
        return m_value;
    }
    uint32_t Wraps() const
    {
        return m_wraps;
    }

private:
    uint32_t m_previous;
    uint64_t m_value;
    uint32_t m_wraps{};
};

struct Snapshot {
    uint64_t dwtBefore{};
    uint64_t systick{};
    uint64_t cpu{};
    uint64_t dwtAfter{};
    uint32_t interrupts{};
    bool pending{};
};

bool ReadSnapshot(DwtClock& clock, Snapshot& sample)
{
    pmu_counters counters{};
    __DSB();
    sample.dwtBefore = clock.Read();
    sample.systick   = Get_SysTick_Cycle_Count();
    hal_pmu_get_counters(&counters);
    sample.dwtAfter = clock.Read();
    __DSB();
    sample.interrupts = Get_SysTick_Count();
    sample.pending    = (SCB->ICSR & SCB_ICSR_PENDSTSET_Msk) != 0;
    if (!counters.initialised || counters.num_counters != 1 ||
        std::strcmp(counters.counters[0].name, "CPU TOTAL") != 0 ||
        std::strcmp(counters.counters[0].unit, "cycles") != 0) {
        return false;
    }
    sample.cpu = counters.counters[0].value;
    return true;
}

bool WaitCycles(DwtClock& clock, uint64_t cycles, uint32_t frequency)
{
    const uint64_t start     = clock.Read();
    const uint32_t tickStart = Get_SysTick_Count();
    const uint64_t timeoutMs = cycles * 1000 / frequency + 1000;
    while (clock.Read() - start < cycles) {
        // A second timebase bounds the wait if CYCCNT stops while interrupts run.
        if (static_cast<uint32_t>(Get_SysTick_Count() - tickStart) > timeoutMs) {
            return false;
        }
    }
    return true;
}

bool InBounds(uint64_t value, uint64_t lower, uint64_t upper)
{
    return value + kTolerance >= lower && value <= upper + kTolerance;
}

bool Measure(uint32_t index,
             const char* kind,
             uint32_t durationUs,
             uint32_t frequency,
             bool maskInterrupts = false)
{
    hal_pmu_init();
    DwtClock clock;
    const uint32_t period  = SysTick->LOAD + 1;
    const uint32_t primask = __get_PRIMASK();
    if (maskInterrupts) {
        // Enter the last eighth of a tick, then mask for a quarter period. This
        // creates one pending wrap without violating the timer's one-tick limit.
        const uint64_t deadline = clock.Read() + frequency / 10;
        while (true) {
            const uint32_t phase = SysTick->VAL;
            if (phase <= period / 8 && phase >= period / 16) {
                break;
            }
            if (clock.Read() > deadline) {
                return false;
            }
        }
        __disable_irq();
        __DSB();
        __ISB();
    }
    Snapshot start, end;
    const uint64_t target = static_cast<uint64_t>(frequency) * durationUs / 1000000;
    const bool sampled    = ReadSnapshot(clock, start) && WaitCycles(clock, target, frequency) &&
                         ReadSnapshot(clock, end);
    if (maskInterrupts) {
        __set_PRIMASK(primask);
        __ISB();
    }
    hal_pmu_final();
    if (!sampled || end.dwtBefore < start.dwtAfter || end.systick < start.systick ||
        end.cpu < start.cpu) {
        std::printf("TIMER error index=%" PRIu32 " reason=counter_read_or_monotonicity\n", index);
        return false;
    }
    const uint64_t lower   = end.dwtBefore - start.dwtAfter;
    const uint64_t upper   = end.dwtAfter - start.dwtBefore;
    const uint64_t systick = end.systick - start.systick;
    const uint64_t cpu     = end.cpu - start.cpu;
    bool passed            = InBounds(systick, lower, upper) && InBounds(cpu, lower, upper) &&
                  start.dwtAfter - start.dwtBefore < period / 4 &&
                  end.dwtAfter - end.dwtBefore < period / 4 && lower >= target;
    if (maskInterrupts) {
        passed = passed && !start.pending && end.pending && upper < period &&
                 start.interrupts == end.interrupts;
    } else if (target >= static_cast<uint64_t>(period) * 2) {
        passed = passed && end.interrupts - start.interrupts >= target / period - 1;
    }
    if (std::strcmp(kind, "dwt_wrap") == 0) {
        passed = passed && clock.Wraps() >= 1;
    }
    if (std::strcmp(kind, "long") == 0) {
        passed = passed && lower > UINT32_MAX && clock.Wraps() >= 1;
    }
    std::printf("TIMER sample index=%" PRIu32 " kind=%s target_us=%" PRIu32 " dwt_start_lo=%" PRIu64
                " dwt_start_hi=%" PRIu64 " dwt_end_lo=%" PRIu64 " dwt_end_hi=%" PRIu64
                " systick_start=%" PRIu64 " systick_end=%" PRIu64 " cpu_start=%" PRIu64
                " cpu_end=%" PRIu64 " irq_start=%" PRIu32 " irq_end=%" PRIu32
                " pending_start=%u pending_end=%u dwt_wraps=%" PRIu32 " status=%s\n",
                index,
                kind,
                durationUs,
                start.dwtBefore,
                start.dwtAfter,
                end.dwtBefore,
                end.dwtAfter,
                start.systick,
                end.systick,
                start.cpu,
                end.cpu,
                start.interrupts,
                end.interrupts,
                static_cast<unsigned>(start.pending),
                static_cast<unsigned>(end.pending),
                clock.Wraps(),
                passed ? "PASS" : "FAIL");
    return passed;
}

bool EnableDwt()
{
    CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
    __DSB();
    __ISB();
    if ((DWT->CTRL & DWT_CTRL_NOCYCCNT_Msk) != 0) {
        return false;
    }
    DWT->CTRL             = (DWT->CTRL & ~DWT_CTRL_CYCDISS_Msk) | DWT_CTRL_CYCCNTENA_Msk;
    const uint32_t before = DWT->CYCCNT;
    for (unsigned int index = 0; index < 1000; ++index) {
        __NOP();
    }
    return DWT->CYCCNT != before;
}
} // namespace

void MainLoop()
{
    const uint32_t frequency = GetSystemCoreClock();
    const uint32_t required =
        SysTick_CTRL_ENABLE_Msk | SysTick_CTRL_TICKINT_Msk | SysTick_CTRL_CLKSOURCE_Msk;
    std::printf("TIMER build id=%s\n", TIMER_VALIDATION_BUILD_ID);
    if (frequency != 400000000 || __get_PRIMASK() != 0 || __get_BASEPRI() != 0 ||
        (SysTick->CTRL & required) != required || SysTick->LOAD + 1 != frequency / 1000 ||
        !EnableDwt()) {
        std::puts("TIMER error reason=clock_systick_or_dwt_unavailable");
        std::puts("TIMER summary count=0 status=FAIL");
        return;
    }
    std::printf("TIMER config version=1 clock_hz=%" PRIu32 " period_cycles=%" PRIu32
                " tolerance_cycles=%" PRIu32 " expected_samples=%" PRIu32 " systick_ctrl=%" PRIu32
                " dwt_ctrl=%" PRIu32 "\n",
                frequency,
                SysTick->LOAD + 1,
                kTolerance,
                kSampleCount,
                SysTick->CTRL,
                DWT->CTRL);
    const uint32_t durations[] = {0, 100, 900, 1100, 10000, 100000, 1000000};
    uint32_t count             = 0;
    bool passed                = true;
    for (const auto duration : durations) {
        for (unsigned int repeat = 0; repeat < 3; ++repeat) {
            passed = Measure(count++, "interval", duration, frequency) && passed;
        }
    }
    // Deliberately start close to a CYCCNT wrap in this standalone diagnostic.
    DWT->CYCCNT = UINT32_MAX - frequency / 1000;
    __DSB();
    __ISB();
    passed = Measure(count++, "dwt_wrap", 10000, frequency) && passed;
    passed = Measure(count++, "pending", 250, frequency, true) && passed;
    passed = Measure(count++, "long", 12000000, frequency) && passed;
    std::printf("TIMER summary count=%" PRIu32 " status=%s\n", count, passed ? "PASS" : "FAIL");
}
