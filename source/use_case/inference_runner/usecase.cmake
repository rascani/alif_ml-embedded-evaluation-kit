#----------------------------------------------------------------------------
#  SPDX-FileCopyrightText: Copyright 2021, 2024-2025 Arm Limited and/or
#  its affiliates <open-source-office@arm.com>
#  SPDX-License-Identifier: Apache-2.0
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#----------------------------------------------------------------------------

# Specify the ML frameworks the use case supports
set(${use_case}_ML_FRAMEWORK "TensorFlowLiteMicro;ExecuTorch")
if (NOT ${ML_FRAMEWORK} IN_LIST ${use_case}_ML_FRAMEWORK)
    message(STATUS "${use_case} does not support ${ML_FRAMEWORK} framework")
    set(${use_case}_supports_${ML_FRAMEWORK} OFF)
    return()
endif ()

set(${use_case}_supports_${ML_FRAMEWORK} ON)

# Append the API to use for this use case
list(APPEND ${use_case}_API_LIST "inference_runner")

USER_OPTION(${use_case}_ACTIVATION_BUF_SZ "Activation buffer size for the chosen model"
    0x00200000
    STRING)

if (${ML_FRAMEWORK} STREQUAL "TensorFlowLiteMicro")
    if (ETHOS_U_NPU_ENABLED)
        set(DEFAULT_MODEL_PATH      ${DEFAULT_MODEL_DIR}/dnn_s_quantized_vela_${ETHOS_U_NPU_CONFIG_ID}.tflite)
    else()
        set(DEFAULT_MODEL_PATH      ${DEFAULT_MODEL_DIR}/dnn_s_quantized.tflite)
    endif()

    if (NOT TARGET_PLATFORM STREQUAL native)
        USER_OPTION(
            ${use_case}_DYNAMIC_MEM_LOAD_ENABLED
            "Allow dynamically loading model and ifm at runtime (valid for FVP only)"
            OFF
            BOOL)
    endif()

    # For non-native targets, for use with the FVPs only.
    if (${${use_case}_DYNAMIC_MEM_LOAD_ENABLED})

        message(STATUS "NOTE: Dynamic memory load enabled. This ${use_case} application will run on FVP only.")

        if (NOT DEFINED DYNAMIC_MODEL_BASE AND DEFINED DYNAMIC_MODEL_SIZE)
            message(FATAL_ERROR "${TARGET_PLATFORM} does not support dynamic load for model files.")
        else()
            set(${use_case}_COMPILE_DEFS
                "DYNAMIC_MODEL_BASE=${DYNAMIC_MODEL_BASE};DYNAMIC_MODEL_SIZE=${DYNAMIC_MODEL_SIZE}")
        endif()

        if (DEFINED DYNAMIC_IFM_BASE AND DEFINED DYNAMIC_IFM_SIZE)
            string(APPEND ${use_case}_COMPILE_DEFS
                ";DYNAMIC_IFM_BASE=${DYNAMIC_IFM_BASE};DYNAMIC_IFM_SIZE=${DYNAMIC_IFM_SIZE}")
        else()
            message(WARNING "${TARGET_PLATFORM} does not support dynamic load for input tensors.")
        endif()

        if (DEFINED DYNAMIC_OFM_BASE AND DEFINED DYNAMIC_OFM_SIZE)
            string(APPEND ${use_case}_COMPILE_DEFS
                ";DYNAMIC_OFM_BASE=${DYNAMIC_OFM_BASE};DYNAMIC_OFM_SIZE=${DYNAMIC_OFM_SIZE}")
        else()
            message(WARNING "${TARGET_PLATFORM} does not support dumping of output tensors.")
        endif()

    else()
        USER_OPTION(${use_case}_MODEL_PATH "NN models file to be used in the evaluation application. Model files must be in tflite format."
            ${DEFAULT_MODEL_PATH}
            FILEPATH)

        # Generate model file
        generate_model_code(
            MODEL_PATH ${${use_case}_MODEL_PATH}
            DESTINATION ${SRC_GEN_DIR}
            NAMESPACE   "arm" "app" "inference_runner")
    endif()

elseif(${ML_FRAMEWORK} STREQUAL "ExecuTorch")
    set(DEFAULT_MODEL_PATH "")

    USER_OPTION(${use_case}_MODEL_PATH "Neural network model file (.pte) to be used in the evaluation application."
        "${DEFAULT_MODEL_PATH}"
        FILEPATH)

    if (COMMAND generate_pte_ops_lib)
        generate_pte_ops_lib(
            MODEL_PATH      "${${use_case}_MODEL_PATH}"
            LIB_NAME        "${use_case}_portable_ops_lib"
            SELECT_OPS_LIST "")

        set(${use_case}_LINK_LIBS ${use_case}_portable_ops_lib)
    endif()

    # Generate model file
    generate_model_code(
        MODEL_PATH ${${use_case}_MODEL_PATH}
        DESTINATION ${SRC_GEN_DIR}
        NAMESPACE   "arm" "app" "inference_runner")
endif()
