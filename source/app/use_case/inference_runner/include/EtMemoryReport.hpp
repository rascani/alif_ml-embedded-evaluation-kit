/*
 * SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates
 * <open-source-office@arm.com>
 * SPDX-License-Identifier: Apache-2.0
 */
#pragma once
#if defined(ET_MEMORY_REPORT)
#include "mlek/fwk/executorch/EtModel.hpp"

namespace arm::app::inference_runner {
size_t EtAllocatedHeapBytes();
bool PrintEtMemory(const fwk::et::EtModel& model, size_t heapBeforeInit, size_t heapAfterInit);
} // namespace arm::app::inference_runner
#endif
