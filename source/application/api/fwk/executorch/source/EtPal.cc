/*
 * SPDX-FileCopyrightText: Copyright 2025 Arm Limited and/or its affiliates
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
#include "ExecuTorch.hpp"

#if defined(MLEK_BAREMETAL)
extern "C" uint64_t Get_SysTick_Cycle_Count(void);
#endif

et_timestamp_t et_pal_current_ticks(void)
{
#if defined(MLEK_BAREMETAL)
    return static_cast<et_timestamp_t>(Get_SysTick_Cycle_Count());
#else
    return 0;
#endif
}

/* For ExecuTorch logging the et_pal_emit_log_message needs to be overridden. */
void et_pal_emit_log_message(
    ET_UNUSED et_timestamp_t timestamp,
    et_pal_log_level_t level,
    const char* filename,
    ET_UNUSED const char* function,
    size_t line,
    const char* message,
    ET_UNUSED size_t length)
{
    printf("%c [ExecuTorch: %s:%zu %s()] %s\n",
        level,
        filename,
        line,
        function,
        message);
}
