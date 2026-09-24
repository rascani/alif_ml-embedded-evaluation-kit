/* SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates
 * <open-source-office@arm.com>
 * SPDX-License-Identifier: Apache-2.0
 */
#include <cstdint>
#include <cstdio>
extern "C" {
#include "timer_alif.h"
uint32_t GetSystemCoreClock(void)
{
    return 400000000;
}
}
extern void MainLoop();

int main()
{
    std::puts("SIMULATOR TIMER CHECK: not physical E8 validation or clock calibration");
    if (Init_SysTick() != 0) {
        return 1;
    }
    MainLoop();
    std::puts("INFO - program terminating...");
    return 0;
}
