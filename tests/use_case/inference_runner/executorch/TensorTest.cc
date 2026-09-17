/*
 * SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates
 * <open-source-office@arm.com>
 * SPDX-License-Identifier: Apache-2.0
 */
#include "mlek/fwk/executorch/EtTensor.hpp"
#include <catch.hpp>

TEST_CASE("ExecuTorch byte tensors expose their signedness without changing storage",
          "[inference_runner][executorch][tensor]")
{
    using namespace arm::app::fwk;
    using executorch::aten::ScalarType;
    using executorch::aten::TensorImpl;
    TensorImpl::SizesType sizes[]    = {1, 4};
    TensorImpl::DimOrderType order[] = {0, 1};
    uint8_t data[]                   = {0, 127, 128, 255};

    for (auto dtype : {ScalarType::Char, ScalarType::Byte, ScalarType::QInt8, ScalarType::QUInt8}) {
        const auto expected = (dtype == ScalarType::Char || dtype == ScalarType::QInt8)
                                  ? iface::TensorType::INT8
                                  : iface::TensorType::UINT8;
        TensorImpl impl(dtype, 2, sizes, data, order);
        executorch::aten::Tensor tensor(&impl);
        et::EtTensor fromImpl(&impl);
        et::EtTensor fromTensor(tensor);
        for (auto* wrapped : {&fromImpl, &fromTensor}) {
            REQUIRE(wrapped->Type() == expected);
            REQUIRE(wrapped->Bytes() == sizeof(data));
            REQUIRE(wrapped->GetNumElements() == 4);
            REQUIRE(wrapped->GetData() == data);
            REQUIRE(wrapped->Shape() == std::vector<size_t>{1, 4});
        }
    }
}
