#----------------------------------------------------------------------------
#  SPDX-FileCopyrightText: Copyright 2025-2026 Arm Limited and/or its
#  affiliates <open-source-office@arm.com>
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

# Limitations
# 1. Arm compiler is not supported.
if (CMAKE_CXX_COMPILER_ID STREQUAL "ARMClang")
    message(
            FATAL_ERROR
            "ExecuTorch does not currently support Arm Compiler. "
            "Use the ML_FRAMEWORK argument to specify a different framework."
    )
endif ()

# 2. Arm Ethos-U65 and Dedicated_Sram are not supported in current revision, but
#    are known to be working in a more recent versions which we need to migrate to.
if (ETHOS_U_NPU_ENABLED)
    if (ETHOS_U_NPU_ID STREQUAL U65)
        message(FATAL_ERROR "Support for Arm Ethos-U65 is currently disabled in this "
                            "experimental branch. Use Arm Ethos-U55 or Arm Ethos-U85")
    endif()
endif()

# Validate pre-requisites.
assert_defined(EXECUTORCH_SRC_PATH)
assert_defined(PYTHON_VENV)
assert_defined(PYTHON)

USER_OPTION(MLEK_EXECUTORCH_SELECTIVE_BUILD
    "Select inference runner operators and registry capacity from its PTE model"
    OFF BOOL)
USER_OPTION(MLEK_EXECUTORCH_SELECT_PRIM_OPS
    "Also select primitive operators from the model in a selective build"
    ON BOOL)
if (MLEK_EXECUTORCH_SELECTIVE_BUILD)
    # The runtime registry is shared by all executables in this build tree.
    if (NOT "${USE_CASE_BUILD}" STREQUAL "inference_runner")
        message(FATAL_ERROR "MLEK_EXECUTORCH_SELECTIVE_BUILD requires "
                            "USE_CASE_BUILD=inference_runner")
    endif()
    if (EXECUTORCH_SELECT_OPS_MODEL OR EXECUTORCH_SELECT_OPS_LIST OR
        EXECUTORCH_SELECT_OPS_YAML OR EXECUTORCH_ENABLE_DTYPE_SELECTIVE_BUILD)
        message(FATAL_ERROR "Use inference_runner_MODEL_PATH with "
            "MLEK_EXECUTORCH_SELECTIVE_BUILD; upstream EXECUTORCH_SELECT_OPS_* "
            "and dtype selection cannot be combined with this option")
    endif()
endif()

# Prepare CMake configuration overrides.
set(EXECUTORCH_BUILD_EXECUTOR_RUNNER            OFF)
set(EXECUTORCH_BUILD_KERNELS_QUANTIZED          ON)
set(EXECUTORCH_BUILD_EXTENSION_RUNNER_UTIL      ON)
set(EXECUTORCH_ENABLE_LOGGING                   ${MLEK_LOG_ENABLE})
set(EXECUTORCH_BUILD_DEVTOOLS                   OFF)
set(EXECUTORCH_ENABLE_EVENT_TRACER              OFF)
set(GFLAGS_INTTYPES_FORMAT                      C99)
set(CMAKE_POSITION_INDEPENDENT_CODE             OFF)

if(TARGET_PLATFORM STREQUAL native)
    set(EXECUTORCH_BUILD_ARM_BAREMETAL          OFF)
    set(EXECUTORCH_BUILD_CORTEX_M               OFF)
    set(EXECUTORCH_BUILD_CPUINFO                ON)
else()
    assert_defined(CMSIS_NN_SRC_PATH)
    assert_defined(CMSIS_SRC_PATH)
    if (NOT EXISTS "${CMSIS_NN_SRC_PATH}/CMakeLists.txt")
        message(FATAL_ERROR "Initialize CMSIS-NN at ${CMSIS_NN_SRC_PATH} before building ExecuTorch")
    endif()
    set(EXECUTORCH_BUILD_ARM_BAREMETAL          ${ETHOS_U_NPU_ENABLED})
    set(EXECUTORCH_BUILD_CORTEX_M               ON)
    set(EXECUTORCH_BUILD_HOST_TARGETS           OFF)
    set(EXECUTORCH_BUILD_CPUINFO OFF CACHE BOOL "No CPU discovery on bare-metal targets" FORCE)
    set(EXECUTORCH_BUILD_PTHREADPOOL OFF CACHE BOOL "No pthreads on bare-metal targets" FORCE)
    set(CMSIS_NN_LOCAL_PATH "${CMSIS_NN_SRC_PATH}" CACHE PATH
        "Use the same CMSIS-NN source as the other ML frameworks" FORCE)
    set(CMSIS_PATH "${CMSIS_SRC_PATH}")
    if (CMAKE_BUILD_TYPE STREQUAL Debug)
        set(CMSIS_OPTIMIZATION_LEVEL "-O0" CACHE STRING "CMSIS-NN optimization level" FORCE)
    else()
        set(CMSIS_OPTIMIZATION_LEVEL "-O3" CACHE STRING "CMSIS-NN optimization level" FORCE)
    endif()
endif()

set(EXECUTORCH_PAL_DEFAULT                      minimal)

# Map ExecuTorch supported log levels
if (${MLEK_LOG_LEVEL} STREQUAL MLEK_LOG_LEVEL_TRACE OR
    ${MLEK_LOG_LEVEL} STREQUAL MLEK_LOG_LEVEL_DEBUG)
    set(EXECUTORCH_LOG_LEVEL                    "Debug")
elseif(${MLEK_LOG_LEVEL} STREQUAL MLEK_LOG_LEVEL_INFO)
    set(EXECUTORCH_LOG_LEVEL                    "Info")
else()
    set(EXECUTORCH_LOG_LEVEL                    "Error")
endif()

# Prevent littering callee/parent scope: Create a block for variables
# needed only by ExecuTorch related configuration.
block(SCOPE_FOR VARIABLES)
    # Ensure Python virtual environment bin location is available.
    set(ENV_PATH "${PYTHON_VENV}/bin:$ENV{PATH}")

    # Override the Python executable set by ExecuTorch's Utils.cmake
    # It expects a conda environment and sets this. We set it here
    # for our virtual environment python to be used instead.
    set(PYTHON_EXECUTABLE ${PYTHON})

    # Set FLATC location - this should always be available (built for host)
    # or else a build will be attempted.
    if (EXISTS ${PYTHON_VENV}/bin/flatc)
        set(FLATC_EXECUTABLE "${PYTHON_VENV}/bin/flatc")
    else()
        message(FATAL_ERROR "flatc executable doesn't exist")
    endif()

    # Add ET main subdirectory
    add_subdirectory(${EXECUTORCH_SRC_PATH}
        ${CMAKE_BINARY_DIR}/executorch EXCLUDE_FROM_ALL)


    if(EXECUTORCH_ENABLE_EVENT_TRACER)
        target_compile_options(executorch INTERFACE -DET_EVENT_TRACER_ENABLED)
        target_compile_options(portable_ops_lib INTERFACE -DET_EVENT_TRACER_ENABLED)
    endif()
endblock()

# Collate the targets for easily linking against.
add_library(mlek_executorch INTERFACE)

target_link_libraries(mlek_executorch INTERFACE
    program_schema
    extension_runner_util)

if (NOT MLEK_EXECUTORCH_SELECTIVE_BUILD)
    target_link_libraries(mlek_executorch INTERFACE quantized_ops_lib)
endif()

# Based on target, link to the correct portable ops library
if (TARGET_PLATFORM STREQUAL native)
    if (NOT MLEK_EXECUTORCH_SELECTIVE_BUILD)
        target_link_libraries(mlek_executorch INTERFACE portable_ops_lib)
    endif()
else()
    if (NOT MLEK_EXECUTORCH_SELECTIVE_BUILD)
        target_link_libraries(mlek_executorch INTERFACE cortex_m_ops_lib)
    endif()
    target_link_libraries(mlek_executorch INTERFACE kernels_util_all_deps)

    if (TARGET executorch_delegate_ethos_u)
        # If Arm Ethos-U NPU driver is defined as a target, we edit its
        # include directory paths for it to be installed as a dependency
        # for the Arm Ethos-U NPU backend within ExecuTorch.
        if (TARGET ethosu_core_driver AND EXECUTORCH_BUILD_ARM_BAREMETAL)
            install(TARGETS ethosu_core_driver EXPORT ExecuTorchTargets)
            get_target_property(_NPU_INTERFACE_INC
                ethosu_core_driver INTERFACE_INCLUDE_DIRECTORIES)
            set_target_properties(ethosu_core_driver
                PROPERTIES INTERFACE_INCLUDE_DIRECTORIES "")

            target_include_directories(ethosu_core_driver PUBLIC
                $<BUILD_INTERFACE:${_NPU_INTERFACE_INC}>
                $<INSTALL_INTERFACE:$<INSTALL_PREFIX>/include>)
        endif()

        # Supress warnings from Arm Ethos-U delegate library
        target_compile_options(executorch_delegate_ethos_u PRIVATE
            -Wno-error=deprecated-declarations
            -Wno-error=unused-parameter)

        # Whole archive needs to be included for the delegate.
        target_link_libraries(mlek_executorch INTERFACE
            "-Wl,--whole-archive"
            $<TARGET_FILE:executorch_delegate_ethos_u>
            "-Wl,--no-whole-archive")

        # Explicitly add dependency as some generators might not
        # add it automatically when only TARGET_FILE is used
        # in linking.
        add_dependencies(mlek_executorch executorch_delegate_ethos_u)
    endif()
endif()

# Provide alias target for rest of projects to use
add_library(meta::executorch ALIAS mlek_executorch)

# Include code generation wrappers from ExecuTorch.
set(EXECUTORCH_ROOT ${EXECUTORCH_SRC_PATH})
include(${EXECUTORCH_SRC_PATH}/tools/cmake/Codegen.cmake)

##############################################################################
# Generate one model-specific registry for portable and custom CPU kernels.
# Full registration libraries must not be linked alongside this library.
##############################################################################
function(generate_selected_pte_ops_lib MODEL_PATH LIB_NAME SELECT_OPS_LIST)
    get_filename_component(ABS_MODEL_PATH "${MODEL_PATH}" ABSOLUTE)
    # Model embedding runs at configure time; keep it in sync with registrations.
    set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${ABS_MODEL_PATH}")
    set(PYTHON_EXECUTABLE "${PYTHON}")
    set(EXECUTORCH_ROOT "${EXECUTORCH_SRC_PATH}")

    gen_selected_ops(
        LIB_NAME "${LIB_NAME}"
        ROOT_OPS "${SELECT_OPS_LIST}"
        OPS_FROM_MODEL "${ABS_MODEL_PATH}")
    # Upstream's generator does not declare the PTE as an input dependency.
    add_custom_command(OUTPUT "${gen_selected_ops_output_yaml}" APPEND
        DEPENDS "${ABS_MODEL_PATH}")

    add_library(${LIB_NAME} INTERFACE)
    # Generate each schema separately: upstream keys custom schemas by operator
    # name without its namespace, so Cortex-M and quantized names can collide.
    foreach(KERNEL_SET portable quantized cortex_m)
        if (NOT TARGET ${KERNEL_SET}_kernels)
            continue()
        endif()
        set(FUNCTIONS_YAML "")
        set(CUSTOM_OPS_YAML "")
        if (KERNEL_SET STREQUAL portable)
            set(FUNCTIONS_YAML "${EXECUTORCH_SRC_PATH}/kernels/portable/functions.yaml")
        elseif (KERNEL_SET STREQUAL quantized)
            set(CUSTOM_OPS_YAML "${EXECUTORCH_SRC_PATH}/kernels/quantized/quantized.yaml")
        else()
            set(CUSTOM_OPS_YAML "${EXECUTORCH_SRC_PATH}/backends/cortex_m/ops/operators.yaml")
        endif()

        set(OPS_LIB "${LIB_NAME}_${KERNEL_SET}")
        set(OPS_DIR "${CMAKE_CURRENT_BINARY_DIR}/${OPS_LIB}")
        file(MAKE_DIRECTORY "${OPS_DIR}")
        add_custom_command(OUTPUT "${OPS_DIR}/selected_operators.yaml"
            COMMAND ${CMAKE_COMMAND} -E copy_if_different
                "${gen_selected_ops_output_yaml}" "${OPS_DIR}/selected_operators.yaml"
            DEPENDS "${gen_selected_ops_output_yaml}")
        generate_bindings_for_kernels(
            LIB_NAME "${OPS_LIB}"
            FUNCTIONS_YAML "${FUNCTIONS_YAML}"
            CUSTOM_OPS_YAML "${CUSTOM_OPS_YAML}")
        gen_operators_lib(
            LIB_NAME "${OPS_LIB}"
            KERNEL_LIBS ${KERNEL_SET}_kernels
            DEPS executorch)
        target_link_libraries(${LIB_NAME} INTERFACE ${OPS_LIB})
    endforeach()

    if (MLEK_EXECUTORCH_SELECT_PRIM_OPS)
        set(PRIM_OPS_DIR "${CMAKE_CURRENT_BINARY_DIR}/${LIB_NAME}/prim_ops")
        set(PRIM_OPS_HEADER "${PRIM_OPS_DIR}/selected_prim_ops.h")
        file(MAKE_DIRECTORY "${PRIM_OPS_DIR}")
        add_custom_command(OUTPUT "${PRIM_OPS_HEADER}"
            COMMAND "${PYTHON}" -m codegen.tools.gen_selected_prim_ops
                "--op-selection-yaml-path=${gen_selected_ops_output_yaml}"
                "--output-dir=${PRIM_OPS_DIR}"
            DEPENDS "${gen_selected_ops_output_yaml}"
                "${EXECUTORCH_SRC_PATH}/codegen/tools/gen_selected_prim_ops.py"
            WORKING_DIRECTORY "${EXECUTORCH_SRC_PATH}")
        # Select the registrations in the existing runtime archive; linking a
        # second registrar would leave the original full primitive set enabled.
        add_custom_target(${LIB_NAME}_prim_ops_header DEPENDS "${PRIM_OPS_HEADER}")
        add_dependencies(executorch ${LIB_NAME}_prim_ops_header)
        target_include_directories(executorch PRIVATE "${PRIM_OPS_DIR}")
        target_compile_definitions(executorch PRIVATE
            ET_PRIM_OPS_SELECTIVE_BUILD EXECUTORCH_ENABLE_PRIM_OPS_SELECTIVE_BUILD)
    endif()

    # An explicit MAX_KERNEL_NUM retains upstream's manual-override semantics.
    if (NOT DEFINED MAX_KERNEL_NUM AND NOT DEFINED CACHE{MAX_KERNEL_NUM})
        if (MLEK_EXECUTORCH_SELECT_PRIM_OPS)
            set(${LIB_NAME}_max_kernel_num_include_dir
                "${CMAKE_CURRENT_BINARY_DIR}/${LIB_NAME}")
            set(REGISTRY_HEADER "${${LIB_NAME}_max_kernel_num_include_dir}/executorch/runtime/kernel/selected_max_kernel_num.h")
            add_custom_command(OUTPUT "${REGISTRY_HEADER}"
                COMMAND "${PYTHON}" -m mlek_tools.gen.gen_et_registry
                    "--oplist-yaml=${gen_selected_ops_output_yaml}"
                    "--output-path=${REGISTRY_HEADER}"
                DEPENDS "${gen_selected_ops_output_yaml}"
                    "${MLEK_ROOT}/scripts/py/mlek_tools/gen/gen_et_registry.py")
            add_custom_target(${LIB_NAME}_max_kernel_num_header
                DEPENDS "${REGISTRY_HEADER}")
        else()
            gen_selected_max_kernel_num(
                LIB_NAME "${LIB_NAME}"
                OPLIST_YAMLS "${gen_selected_ops_output_yaml}")
        endif()
        target_include_directories(executorch_core PRIVATE
            "${${LIB_NAME}_max_kernel_num_include_dir}")
        add_dependencies(executorch_core ${LIB_NAME}_max_kernel_num_header)
    endif()
endfunction()

##############################################################################
# This function generates a portable ops library for the PTE model file.
# @param[in]    MODEL_PATH      path to a PTE file
# @param[in]    LIB_NAME        output target library name.
# @param[in]    SELECT_OPS_LIST ops list that should always be included
##############################################################################
function(generate_pte_ops_lib)

    set(oneValueArgs MODEL_PATH LIB_NAME SELECT_OPS_LIST)
    cmake_parse_arguments(PARSED "" "${oneValueArgs}" "" ${ARGN})

    if (MLEK_EXECUTORCH_SELECTIVE_BUILD)
        generate_selected_pte_ops_lib("${PARSED_MODEL_PATH}" "${PARSED_LIB_NAME}"
            "${PARSED_SELECT_OPS_LIST}")
        return()
    endif()

    if (NOT EXECUTORCH_BUILD_CORTEX_M)
        message(STATUS "Skipping custom portable ops lib generation. "
                       "Generation of PTE specific portable ops lib "
                       "is required only for bare-metal Arm targets.")
        return()
    endif()

    # Absolute paths for passing into python script
    get_filename_component(ABS_MODEL_PATH ${PARSED_MODEL_PATH} ABSOLUTE)

    # Ensure Python virtual environment bin location is available.
    set(ENV_PATH "${PYTHON_VENV}/bin:$ENV{PATH}")
    set(EXECUTORCH_ROOT ${EXECUTORCH_SRC_PATH})

    # Override the Python executable set by ExecuTorch's Utils.cmake
    # It expects a conda environment and sets this. We set it here
    # for our virtual environment python to be used instead.
    set(PYTHON_EXECUTABLE ${PYTHON})

    message(STATUS "Attempting PTE ops library generation: ${PARSED_LIB_NAME}")
    message(STATUS "    PTE file: ${PARSED_MODEL_PATH}")
    message(STATUS "    Select ops list: ${PARSED_SELECT_OPS_LIST}")

    execute_process(
        COMMAND ${PYTHON_EXECUTABLE}
            "${EXECUTORCH_SRC_PATH}/codegen/tools/gen_oplist.py"
            --model_file_path=${ABS_MODEL_PATH}
            --output_path=${CMAKE_CURRENT_BINARY_DIR}/${PARSED_LIB_NAME}-ops.yaml
        COMMAND_ERROR_IS_FATAL  ANY
        COMMAND_ECHO            STDOUT
        OUTPUT_VARIABLE         OPS_YML_GEN_RESULT)

    message(DEBUG "Ops report for ${PARSED_LIB_NAME}:"
                  "${OPS_YML_GEN_RESULT}")

    # Does the op list contain any aten or dim order ops? If so, we can provide
    # the path to PTE file for ops lib gen. Otherwise, we pass in an empty argument.
    if (OPS_YML_GEN_RESULT MATCHES "aten::" OR
        OPS_YML_GEN_RESULT MATCHES "dim_order_ops::")
        set(PTE_FOR_OPS_LIB ${ABS_MODEL_PATH})
    else()
        message(STATUS "No aten or dim_order_ops found in ${PARSED_MODEL_PATH}")
        set(PTE_FOR_OPS_LIB "")
    endif()

    # Generate C++ bindings to register kernels into both PyTorch (for AOT) and
    # Executorch (for runtime). Here select all ops in functions.yaml
    if ("${PARSED_SELECT_OPS_LIST}" STREQUAL "" AND
        "${PTE_FOR_OPS_LIB}" STREQUAL "")
        message(STATUS "No portable ops library needs to be generated.")
        return()
    endif()

    gen_selected_ops(
        LIB_NAME                "${PARSED_LIB_NAME}"
        OPS_SCHEMA_YAML         ""
        ROOT_OPS                "${PARSED_SELECT_OPS_LIST}"
        INCLUDE_ALL_OPS         ""
        OPS_FROM_MODEL          "${PTE_FOR_OPS_LIB}"
        DTYPE_SELECTIVE_BUILD   "${EXECUTORCH_ENABLE_DTYPE_SELECTIVE_BUILD}"
    )

    generate_bindings_for_kernels(
        LIB_NAME                "${PARSED_LIB_NAME}"
        FUNCTIONS_YAML          "${EXECUTORCH_SRC_PATH}/kernels/portable/functions.yaml"
        DTYPE_SELECTIVE_BUILD   "${EXECUTORCH_ENABLE_DTYPE_SELECTIVE_BUILD}"
    )

    gen_operators_lib(
        LIB_NAME                "${PARSED_LIB_NAME}"
        KERNEL_LIBS             portable_kernels
        DEPS                    executorch
        DTYPE_SELECTIVE_BUILD   "${EXECUTORCH_ENABLE_DTYPE_SELECTIVE_BUILD}"
    )
endfunction()
