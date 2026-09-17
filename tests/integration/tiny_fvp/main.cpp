/* SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates
 * <open-source-office@arm.com>
 * SPDX-License-Identifier: Apache-2.0
 */
#include "platform_pmu.h"
#include <cstdint>
#include <cstdio>
extern void MainLoop();
extern "C" void hal_pmu_init() {}
extern "C" void hal_pmu_final() {}
extern "C" void hal_pmu_reset() {}
extern "C" void hal_pmu_get_counters(pmu_counters* counters)
{
    counters->num_counters = 1;
    counters->initialised  = true;
    counters->counters[0]  = {
        *reinterpret_cast<volatile uint32_t*>(0xE0001004), "CPU TOTAL", "cycles"};
}
int main()
{
    *reinterpret_cast<volatile uint32_t*>(0xE000EDFC) |= (1UL << 24);
    *reinterpret_cast<volatile uint32_t*>(0xE0001000) |= 1UL;
    std::puts("SIMULATOR PROBE: E8 runner/runtime archives; Corstone startup and DWT timer. Not E8 "
              "timing.");
    MainLoop();
    std::puts("INFO - program terminating...");
    return 0;
}
