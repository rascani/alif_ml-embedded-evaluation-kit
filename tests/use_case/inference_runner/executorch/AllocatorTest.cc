/*
 * SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates
 * <open-source-office@arm.com>
 * SPDX-License-Identifier: Apache-2.0
 */
#include "mlek/fwk/executorch/EtMemoryAllocator.hpp"
#include <catch.hpp>

TEST_CASE("ExecuTorch allocator reports actual padding and retains its high-water mark",
          "[inference_runner][executorch][allocator]")
{
    alignas(16) uint8_t storage[128];
    for (size_t offset : {0, 1}) {
        arm::app::fwk::et::EtMemoryAllocator allocator(sizeof(storage) - offset, storage + offset);
        for (size_t size : {3, 16, 5, 1}) {
            auto* allocation = static_cast<uint8_t*>(allocator.allocate(size, 16));
            REQUIRE(allocation != nullptr);
            const size_t consumed = allocation + size - (storage + offset);
            REQUIRE(allocator.UsedSizeCurrent() == consumed);
            REQUIRE(allocator.UsedSizePeak() == consumed);
            REQUIRE(allocator.FreeSize() == allocator.size() - consumed);
        }
        const size_t peak = allocator.UsedSizePeak();
        REQUIRE(allocator.allocate(sizeof(storage), 16) == nullptr);
        REQUIRE(allocator.UsedSizeCurrent() == peak);
        allocator.reset();
        REQUIRE(allocator.UsedSizeCurrent() == 0);
        REQUIRE(allocator.UsedSizePeak() == peak);
        REQUIRE(allocator.allocate(1, 1) != nullptr);
        REQUIRE(allocator.UsedSizeCurrent() == 1);
        REQUIRE(allocator.UsedSizePeak() == peak);
        allocator.ResetPeak();
        REQUIRE(allocator.UsedSizeCurrent() == 1);
        REQUIRE(allocator.UsedSizePeak() == 1);
    }
}
