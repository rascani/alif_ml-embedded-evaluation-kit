/*
 * SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates
 * <open-source-office@arm.com>
 * SPDX-License-Identifier: Apache-2.0
 */
#pragma once
#include "mlek/fwk/iface/Model.hpp"
namespace arm::app::inference_runner {
bool ValidateInference(fwk::iface::Model& model);
}
