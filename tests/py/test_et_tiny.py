# SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates
# <open-source-office@arm.com>
# SPDX-License-Identifier: Apache-2.0
"""Reject ET memory double-counting, missing validation, and misattributed flash."""

import importlib
from pathlib import Path
import sys
import unittest

from test_tflm_tiny_board import fixture

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/py"))
results = importlib.import_module("tflm_tiny_results")
flash = importlib.import_module("et_tiny_flash")


def et_fixture() -> tuple[dict, str]:
    """Return a completed ET boot with planned buffers already included in its method pool."""
    manifest, text = fixture()
    manifest["framework"] = "ExecuTorch"
    manifest["models"]["kws"].update(
        planned_bytes=1000,
        arena_reserved_bytes=4096,
        temp_reserved_bytes=512,
        runtime_static_bytes=80,
        validation_samples=3,
    )
    records = """INFO - MEMORY et_init method_peak=1500 temp_peak=40
INFO - MEMORY et_invoke heap_before=8000 heap_after=8000
INFO - MEMORY et_method reserved=4096 planned=1000 runtime_and_inputs=500 used=1500 peak=1500
INFO - MEMORY et_temp reserved=512 used=0 peak=200
INFO - MEMORY et_outside model_object=100 init_heap_delta=300 persistent=400
INFO - MEMORY et_total pools_plus_persistent=2100
INFO - VALIDATION sample index=0 status=PASS
INFO - VALIDATION sample index=1 status=PASS
INFO - VALIDATION sample index=2 status=PASS
INFO - VALIDATION summary count=3 status=PASS reference=lowered_python_int8
"""
    text = (
        text[: text.index("INFO - MEMORY arena")]
        + records
        + text[text.index("INFO - Inference completed.") :]
    )
    return manifest, text


class EtTinyTests(unittest.TestCase):
    """Check the ET-specific parser and attribution boundaries."""

    def test_ram_includes_planned_once_and_static_registry(self):
        """Add pooled memory, retained heap/model storage, and ELF static RAM exactly once."""
        manifest, text = et_fixture()
        row = results.parse_boot(text, manifest)
        self.assertEqual(row["ram_accounted_peak_bytes"], 2180)
        self.assertEqual(row["et_method_planned_bytes"], 1000)
        self.assertEqual(row["validation_samples"], 3)
        self.assertEqual(row["mean_us"], 2)

    def test_inconsistent_memory_and_outputs_rejected(self):
        """Missing checks, wrong outputs, heap growth, and planned-buffer double counts fail."""
        manifest, text = et_fixture()
        for before, after in (
            ("pools_plus_persistent=2100", "pools_plus_persistent=3100"),
            ("planned=1000", "planned=999"),
            ("reserved=512", "reserved=100"),
            ("heap_after=8000", "heap_after=8200"),
            ("index=1 status=PASS", "index=1 status=FAIL"),
            ("index=1 status=PASS", "index=2 status=PASS"),
            ("VALIDATION summary", "missing summary"),
            ("lowered_python_int8", "different_reference"),
        ):
            with self.subTest(before=before), self.assertRaises(ValueError):
                results.parse_boot(text.replace(before, after), manifest)

    def test_native_reference_must_match_manifest(self):
        """Accept the supplied native reference and reject a mislabeled Python reference."""
        manifest, text = et_fixture()
        manifest["models"]["kws"]["validation_reference"] = "cortex_m_native_int8"
        native = text.replace("lowered_python_int8", "cortex_m_native_int8")
        self.assertEqual(results.parse_boot(native, manifest)["validation_samples"], 3)
        with self.assertRaises(ValueError):
            results.parse_boot(text, manifest)

    def test_diagnostic_heap_growth_is_separate_from_inference(self):
        """Accept newlib's reporting allocation while still rejecting inference heap changes."""
        manifest, text = et_fixture()
        manifest["models"]["kws"]["heap_measurement_scope"] = "inference_batch_v1"
        text = text.replace(
            "MEMORY et_invoke heap_before=8000 heap_after=8000",
            "MEMORY et_invoke heap_before=8000 heap_after=8000 scope=inference_batch_v1\n"
            "INFO - MEMORY et_diagnostics heap_before=8000 heap_after=8200",
        )
        row = results.parse_boot(text, manifest)
        self.assertEqual(row["ram_accounted_peak_bytes"], 2180)
        self.assertEqual(row["invoke_heap_delta_bytes"], 0)
        self.assertEqual(row["diagnostic_heap_delta_bytes"], 200)
        for before, after in (
            (
                "et_invoke heap_before=8000 heap_after=8000",
                "et_invoke heap_before=8000 heap_after=8200",
            ),
            ("scope=inference_batch_v1", "scope=handler_v1"),
            ("MEMORY et_diagnostics", "missing diagnostics"),
        ):
            with self.subTest(before=before), self.assertRaises(ValueError):
                results.parse_boot(text.replace(before, after), manifest)

    def test_registry_kernels_and_fixture_ownership(self):
        """Keep generated dispatch bindings while excluding fixtures and the PAL."""
        for section, owner, expected in (
            (".text", "libexecutorch_core.a(method.cpp.obj)", "executorch_core"),
            (".text", "libexecutorch_core.a(operator_registry.cpp.obj)", "registry"),
            (
                ".text",
                "libinference_runner_portable_ops_lib_cortex_m.a(binding.cpp.obj)",
                "registry",
            ),
            (".text", "libcortex_m_kernels.a(op_conv.cpp.obj)", "kernels"),
            (".text", "libcmsis-nn.a(arm_convolve_s8.c.obj)", "cmsis_nn"),
            (".text", "EtPal.cc.obj", "platform_startup"),
            (
                ".rodata.str1.4",
                "libinference_runner_portable_ops_lib_cortex_m.a(binding.cpp.obj)",
                "shared_merged_strings",
            ),
            (
                ".rodata.kValidationInputs",
                "libinference_runner.a(Validation.cc.obj)",
                "validation_fixtures",
            ),
        ):
            with self.subTest(owner=owner):
                entry = flash.Contribution(".readonly.at_mram", section, 0x80001000, 16, owner)
                self.assertEqual(flash.category(entry), expected)

    def test_function_qualified_string_pools(self):
        """Keep size-optimized string pools separate from both runtimes' code."""
        shared_flash = importlib.import_module("tflm_tiny_flash")
        for classifier, owner, ordinary_category in (
            (flash.category, "libexecutorch_core.a(tensor_util.cpp.obj)", "executorch_core"),
            (shared_flash.category, "libtflu.a(micro_interpreter.cc.obj)", "tflm"),
        ):
            for section, is_pool in (
                (".rodata.str1.4", True),
                (".rodata._ZN10executorch7runtime13get_dim_orderE.str1.1", True),
                (".rodata._Z4funcv.str4.4", True),
                (".rodata.strange_table", False),
                (".rodata._Z4funcv", False),
                (".rodata.CSWTCH.303", False),
            ):
                with self.subTest(owner=owner, section=section):
                    entry = flash.Contribution(".readonly.at_mram", section, 0x80001000, 16, owner)
                    expected = "shared_merged_strings" if is_pool else ordinary_category
                    self.assertEqual(classifier(entry), expected)

    def test_direct_input_bundle_rejects_staging_allocation(self):
        """Require the firmware to report the input allocation expected by its manifest."""
        manifest, text = et_fixture()
        manifest["models"]["kws"]["input_pool_allocation_bytes"] = 0
        allocation = "INFO - Inputs allocated: 0 bytes.\n"
        row = results.parse_boot(allocation + text, manifest)
        self.assertEqual(row["input_pool_allocation_bytes"], 0)
        for record in ("", allocation * 2, allocation.replace("0 bytes", "644 bytes")):
            with self.subTest(record=record), self.assertRaises(ValueError):
                results.parse_boot(record + text, manifest)


if __name__ == "__main__":
    unittest.main()
