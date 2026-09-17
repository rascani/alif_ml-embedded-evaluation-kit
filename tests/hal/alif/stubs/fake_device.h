/* SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates
 * <open-source-office@arm.com> SPDX-License-Identifier: Apache-2.0 */
#pragma once
#include <stdint.h>

struct fake_systick {
    uint32_t VAL;
    uint32_t LOAD;
};
struct fake_scb {
    uint32_t ICSR;
};

extern struct fake_systick test_systick;
struct fake_scb* read_scb(void);

#define SysTick                         (&test_systick)
#define SCB                             read_scb()
#define SysTick_VAL_CURRENT_Msk         0x00ffffffu
#define SCB_ICSR_PENDSTSET_Msk          (1u << 26)
#define SysTick_IRQn                    (-1)
#define __NVIC_PRIO_BITS                3
#define __WEAK                          __attribute__((weak))
#define __NOP()                         ((void)0)
#define NVIC_DisableIRQ(irq)            ((void)(irq))
#define NVIC_EnableIRQ(irq)             ((void)(irq))
#define NVIC_SetPriority(irq, priority) ((void)(irq), (void)(priority))
#define GetSystemCoreClock()            1000000u
#define SysTick_Config(ticks)           ((void)(ticks), 0)
