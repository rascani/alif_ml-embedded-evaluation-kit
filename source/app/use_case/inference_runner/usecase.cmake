#----------------------------------------------------------------------------
#  SPDX-FileCopyrightText: Copyright 2021, 2024-2026 Arm Limited and/or
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
    set(${use_case}_supports_${ML_FRAMEWORK} OFF)
    return()
endif ()

set(${use_case}_supports_${ML_FRAMEWORK} ON)

# Append the API to use for this use case
list(APPEND ${use_case}_API_LIST "inference_runner")

USER_OPTION(${use_case}_MODEL_IN_EXT_FLASH "Run model from external flash"
    OFF
    BOOL)
USER_OPTION(${use_case}_ACTIVATION_BUF_SZ "Activation buffer size for the chosen model"
    0x00200000
    STRING)

USER_OPTION(${use_case}_BENCHMARK_ENABLED "Run a repeatable CPU inference benchmark"
    OFF BOOL)
USER_OPTION(${use_case}_WARMUP_COUNT "Additional warm-ups after the first timed inference"
    10 STRING)
USER_OPTION(${use_case}_ITERATION_COUNT "Number of measured steady-state inferences"
    100 STRING)
USER_OPTION(${use_case}_BUILD_ID "Optional firmware identity for benchmark capture"
    "" STRING)
if (${use_case}_BUILD_ID)
    if (NOT ${use_case}_BUILD_ID MATCHES "^[A-Za-z0-9_-]+$")
        message(FATAL_ERROR "Invalid benchmark build ID")
    endif()
    list(APPEND ${use_case}_COMPILE_DEFS
        "BENCHMARK_BUILD_ID=\"${${use_case}_BUILD_ID}\"")
endif()
if (${use_case}_BENCHMARK_ENABLED)
    foreach(COUNT_OPTION WARMUP_COUNT ITERATION_COUNT)
        set(COUNT_VALUE "${${use_case}_${COUNT_OPTION}}")
        if (NOT COUNT_VALUE MATCHES "^(0|[1-9][0-9]*)$" OR COUNT_VALUE GREATER 1000)
            message(FATAL_ERROR "${use_case}_${COUNT_OPTION} must be an integer from 0 to 1000")
        endif()
    endforeach()
    if (${use_case}_ITERATION_COUNT LESS 1)
        message(FATAL_ERROR "${use_case}_ITERATION_COUNT must be at least 1")
    endif()
    if (ETHOS_U_NPU_ENABLED OR ${use_case}_DYNAMIC_MEM_LOAD_ENABLED)
        message(FATAL_ERROR "Benchmark mode requires a CPU-only, embedded model")
    endif()
    if (NOT TARGET_PLATFORM STREQUAL "native" AND NOT CPU_PROFILE_ENABLED)
        message(FATAL_ERROR "Benchmark mode requires CPU_PROFILE_ENABLED=ON")
    endif()
    if (MLEK_LOG_ENABLE AND NOT MLEK_LOG_LEVEL STREQUAL "MLEK_LOG_LEVEL_INFO")
        message(FATAL_ERROR "Benchmark capture requires INFO logging")
    elseif (NOT MLEK_LOG_ENABLE)
        message(STATUS "Silent benchmark build: for size analysis; UART capture is unavailable")
    endif()
    list(APPEND ${use_case}_COMPILE_DEFS
        "INFERENCE_RUNNER_BENCHMARK=1"
        "INFERENCE_RUNNER_WARMUP_COUNT=${${use_case}_WARMUP_COUNT}"
        "INFERENCE_RUNNER_ITERATION_COUNT=${${use_case}_ITERATION_COUNT}")
endif()

if (ML_FRAMEWORK STREQUAL "ExecuTorch")
    if (${use_case}_DYNAMIC_MEM_LOAD_ENABLED)
        message(FATAL_ERROR "Dynamic model loading is only supported with TensorFlowLiteMicro")
    endif()

    USER_OPTION(${use_case}_MODEL_PATH "ExecuTorch program (.pte) to embed in the application."
        ""
        FILEPATH)
    if (NOT EXISTS "${${use_case}_MODEL_PATH}")
        message(FATAL_ERROR "Set ${use_case}_MODEL_PATH to an existing .pte file")
    endif()

    USER_OPTION(${use_case}_ET_MEMORY_REPORT "Report ExecuTorch pool and persistent RAM" OFF BOOL)
    USER_OPTION(${use_case}_MODEL_ID "Model identifier printed in benchmark records"
        "inference_runner" STRING)
    USER_OPTION(${use_case}_VALIDATION_HEADER "Generated int8 validation fixtures" "" STRING)
    if (${use_case}_ET_MEMORY_REPORT)
        if (NOT ${use_case}_MODEL_ID MATCHES "^[A-Za-z0-9_-]+$")
            message(FATAL_ERROR "Invalid benchmark model ID")
        endif()
        file(SHA256 "${${use_case}_MODEL_PATH}" BENCHMARK_MODEL_SHA256)
        list(APPEND ${use_case}_COMPILE_DEFS "ET_MEMORY_REPORT=1"
            "BENCHMARK_MODEL_ID=\"${${use_case}_MODEL_ID}\""
            "BENCHMARK_MODEL_SHA256=\"${BENCHMARK_MODEL_SHA256}\"")
    endif()
    if (${use_case}_VALIDATION_HEADER)
        configure_file("${${use_case}_VALIDATION_HEADER}"
            "${INC_GEN_DIR}/InferenceValidationData.hpp" COPYONLY)
        list(APPEND ${use_case}_COMPILE_DEFS "INFERENCE_VALIDATION=1")
    endif()

    generate_model_code(
        MODEL_PATH "${${use_case}_MODEL_PATH}"
        DESTINATION ${SRC_GEN_DIR}
        NAMESPACE "arm" "app" "inference_runner")

    if (COMMAND generate_pte_ops_lib)
        generate_pte_ops_lib(
            MODEL_PATH "${${use_case}_MODEL_PATH}"
            LIB_NAME "${use_case}_portable_ops_lib"
            SELECT_OPS_LIST "")
        if (TARGET ${use_case}_portable_ops_lib)
            set(${use_case}_LINK_LIBS ${use_case}_portable_ops_lib)
        endif()
    endif()
    return()
endif()

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

USER_OPTION(MLEK_TFLM_SELECTIVE_BUILD
    "Select inference runner TFLM operators and resolver capacity from its model"
    OFF BOOL)
USER_OPTION(MLEK_TFLM_SELECT_INT8_OPS
    "Select CMSIS-NN int8 registrations when every node of an operator is compatible"
    OFF BOOL)
USER_OPTION(${use_case}_TFLM_MEMORY_AUDIT
    "Record TFLM arena peaks and model initialization heap usage" OFF BOOL)
# TFLM's allocator base classes are built without RTTI, including in native builds.
set_property(SOURCE "${CMAKE_CURRENT_LIST_DIR}/src/TflmMemoryAudit.cc"
    APPEND PROPERTY COMPILE_OPTIONS -fno-rtti)
USER_OPTION(${use_case}_MODEL_ID "Model identifier printed in benchmark records"
    "inference_runner" STRING)
if (${use_case}_TFLM_MEMORY_AUDIT AND ${use_case}_DYNAMIC_MEM_LOAD_ENABLED)
    message(FATAL_ERROR "TFLM memory audit requires an embedded model")
endif()
if (MLEK_TFLM_SELECTIVE_BUILD AND ${use_case}_DYNAMIC_MEM_LOAD_ENABLED)
    message(FATAL_ERROR "MLEK_TFLM_SELECTIVE_BUILD requires an embedded model; "
                        "disable inference_runner_DYNAMIC_MEM_LOAD_ENABLED")
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

    if (${use_case}_TFLM_MEMORY_AUDIT)
        if (NOT ${use_case}_MODEL_ID MATCHES "^[A-Za-z0-9_-]+$")
            message(FATAL_ERROR "Model ID must contain only letters, digits, underscores or hyphens")
        endif()
        file(SHA256 "${${use_case}_MODEL_PATH}" BENCHMARK_MODEL_SHA256)
        list(APPEND ${use_case}_COMPILE_DEFS "TFLM_MEMORY_AUDIT=1"
            "BENCHMARK_MODEL_ID=\"${${use_case}_MODEL_ID}\""
            "BENCHMARK_MODEL_SHA256=\"${BENCHMARK_MODEL_SHA256}\"")
    endif()

    # Generate model file
    generate_model_code(
        MODEL_PATH ${${use_case}_MODEL_PATH}
        DESTINATION ${SRC_GEN_DIR}
        NAMESPACE   "arm" "app" "inference_runner")

    if (MLEK_TFLM_SELECTIVE_BUILD)
        get_filename_component(MODEL_PATH "${${use_case}_MODEL_PATH}" ABSOLUTE)
        set(RESOLVER_HEADER
            "${TENSORFLOW_SRC_PATH}/tensorflow/lite/micro/micro_mutable_op_resolver.h")
        set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS
            "${MODEL_PATH}" "${RESOLVER_HEADER}"
            "${MLEK_SCRIPTS_DIR}/py/mlek_tools/gen/gen_tflm_resolver.py"
            "${MLEK_SCRIPTS_DIR}/py/mlek_tools/gen/tflm_registration.py"
            "${MLEK_SCRIPTS_DIR}/py/mlek_tools/gen/templates/SelectedTflmModel.hpp.template")
        foreach(KERNEL_HEADER add conv depthwise_conv fully_connected pooling softmax)
            set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS
                "${TENSORFLOW_SRC_PATH}/tensorflow/lite/micro/kernels/${KERNEL_HEADER}.h")
        endforeach()
        set(INT8_SELECTION_ARGS "")
        if (MLEK_TFLM_SELECT_INT8_OPS)
            list(APPEND INT8_SELECTION_ARGS --select-int8)
        endif()
        execute_process(
            COMMAND ${CMAKE_COMMAND} -E env
                "PYTHONPATH=${MLEK_SCRIPTS_DIR}/py:$ENV{PYTHONPATH}"
                ${PYTHON} -m mlek_tools.gen.gen_tflm_resolver
                --model-path "${MODEL_PATH}"
                --resolver-header "${RESOLVER_HEADER}"
                --output-dir "${INC_GEN_DIR}"
                ${INT8_SELECTION_ARGS}
            COMMAND_ERROR_IS_FATAL ANY)
        add_library(${use_case}_tflm_ops INTERFACE)
        target_compile_definitions(${use_case}_tflm_ops INTERFACE MLEK_TFLM_SELECTIVE_BUILD=1)
        set(${use_case}_LINK_LIBS ${use_case}_tflm_ops)
    endif()
endif()
