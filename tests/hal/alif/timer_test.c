/*
 * SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates
 * <open-source-office@arm.com>
 * SPDX-License-Identifier: Apache-2.0
 */
#include <assert.h>

/* Compile the production timer against simulated registers and inject interrupts
 * between its register reads, including the case where tick_count has not advanced. */
#include "../../../source/hal/source/platform/alif/source/timer_alif.c"

struct fake_systick test_systick;
static struct fake_scb test_scb;
static unsigned reads;
static unsigned event;

struct fake_scb* read_scb(void)
{
    if (++reads == 2) {
        if (event == 1) {
            SysTick_Handler();
            test_scb.ICSR    = 0;
            test_systick.VAL = 949;
        } else if (event == 2) {
            test_scb.ICSR    = SCB_ICSR_PENDSTSET_Msk;
            test_systick.VAL = 999;
        }
    }
    return &test_scb;
}

static void set_counter(uint32_t ticks, uint32_t value, bool pending, unsigned next_event)
{
    tick_count        = ticks;
    test_systick.LOAD = 999;
    test_systick.VAL  = value;
    test_scb.ICSR     = pending ? SCB_ICSR_PENDSTSET_Msk : 0;
    event             = next_event;
    reads             = 0;
}

int main(void)
{
    set_counter(5, 799, false, 0);
    assert(Get_SysTick_Cycle_Count() == 5200);
    set_counter(5, 0, false, 1);
    assert(Get_SysTick_Cycle_Count() == 6050);
    assert(reads == 4); /* Interrupt during read must retry. */
    set_counter(5, 0, false, 2);
    assert(Get_SysTick_Cycle_Count() == 6000);
    assert(reads == 4); /* Wrap becoming pending must retry. */
    set_counter(5, 949, true, 0);
    assert(Get_SysTick_Cycle_Count() == 6050);
    set_counter(5, 949, true, 1);
    assert(Get_SysTick_Cycle_Count() == 6050);
    assert(reads == 4); /* Pending interrupt serviced during read. */

    set_counter(5, 10, false, 0);
    uint64_t before = Get_SysTick_Cycle_Count();
    set_counter(5, 900, true, 0);
    uint64_t after = Get_SysTick_Cycle_Count();
    assert(after - before == 110);
    set_counter(6, 800, false, 0);
    assert(Get_SysTick_Cycle_Count() - after == 100);

    set_counter(5000000, 799, false, 0);
    assert(Get_SysTick_Cycle_Count() == 5000000200ULL);
    platform_init_counters();
    pmu_counters start = {0}, end = {0};
    platform_get_counters(&start);
    set_counter(5000003, 499, false, 0);
    platform_get_counters(&end);
    assert(start.initialised && end.initialised && end.num_counters == 1);
    assert(end.counters[0].value - start.counters[0].value == 3300);
    puts("Alif SysTick rollover and multi-tick counter tests passed");
    return 0;
}
