# SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates
# <open-source-office@arm.com>
# SPDX-License-Identifier: Apache-2.0
"""Verify flash attribution excludes RAM and discarded/debug sections without double counts."""

import importlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/py"))
flash = importlib.import_module("tflm_tiny_flash")


def fixture() -> tuple[str, dict]:
    """Return a small map with known library contributions, aliases, and padding."""
    text = """Discarded input sections
 .text 0x00000000 0x100 lib/libtflu.a(unused.cc.obj)
Linker script and memory map
.readonly.at_mram
                0x80001000 0x50
 .text          0x80001000 0x10 lib/libtflu.a(micro_allocator.cc.obj)
                0x80001000 allocator
                0x80001000 allocator_alias
 .text          0x80001010 0x8 lib/libcmsis-nn.a(arm_convolve_s8.c.obj)
 .text          0x80001018 0x4 lib/libtflu.a(micro_log.cc.obj)
 .text._ZN6tflite22MicroMutableOpResolverFindOp
                0x8000101c 0x4 lib/libinference_runner.a(MainLoop.cc.obj)
 nn_model       0x80001020 0x10 lib/libinference_runner.a(model.tflite.cc.obj)
 .text.memcpy   0x80001030 0x8 /toolchain/libg.a(libc_a-memcpy.o)
 .text          0x80001038 0x8 lib/libcmsis_device.a(Driver_IO.c.obj)
 .text          0x80001040 0x4 lib/libml_framework_tflm.a(TflmModel.cc.obj)
 .rodata.str1.1
                0x80001044 0x4 lib/libinference_runner.a(TflmMemoryAudit.cc.obj)
                         0x100 (size before relaxing)
 *fill*         0x80001048 0x8
.data.dtcm.at_mram
                0x20000000 0x4 load address 0x80001050
 .data          0x20000000 0x4 /toolchain/libg.a(libc_a-impure.o)
.bss.sram       0x02000000 0x40000
 .bss           0x02000000 0x40000 lib/libinference_runner.a(MainLoop.cc.obj)
.debug_info     0x00000000 0x10000
 .debug_info    0x00000000 0x10000 lib/libtflu.a(micro_allocator.cc.obj)
"""
    sections = {
        ".readonly.at_mram": {"bytes": 80, "address": "0x80001000"},
        ".data.dtcm.at_mram": {"bytes": 4, "address": "0x20000000"},
        ".bss.sram": {"bytes": 262144, "address": "0x02000000"},
        ".debug_info": {"bytes": 65536, "address": "0x0"},
    }
    return text, sections


class FlashAttributionTests(unittest.TestCase):
    """Check ownership attribution and a full image-size reconciliation."""

    def test_retained_sections_and_reconciliation(self):
        """Exclude discarded/RAM/debug bytes, keep the resolver, and isolate shared libraries."""
        text, sections = fixture()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "sections.json").write_text(json.dumps(sections), encoding="utf-8")
            (root / "mlek_inference_runner.map").write_text(text, encoding="utf-8")
            (root / "mram.bin").write_bytes(bytes(88))
            (root / "mlek_inference_runner.axf").write_bytes(b"ELF fixture")
            result, entries = flash.analyze_model(root, {"bytes": 16, "flash_total_bytes": 88})
        self.assertEqual(len(entries), 10)
        self.assertEqual(result["filtered_runtime_bytes"], 28)
        self.assertEqual(result["filtered_model_runtime_bytes"], 44)
        self.assertEqual(result["shared_toolchain_bytes"], 12)
        self.assertEqual(result["framework_logging_bytes"], 4)
        self.assertEqual(result["framework_adapter_bytes"], 4)
        self.assertEqual(result.get("runner_diagnostics_bytes", 0), 0)
        self.assertEqual(result["shared_merged_strings_bytes"], 4)
        self.assertEqual(result["linker_tables_padding_bytes"], 12)
        self.assertEqual(result["excluded_from_filtered_bytes"], 44)
        self.assertEqual(sum(entry["size"] for entry in entries) + 12, 88)

    def test_overlapping_or_outside_ranges_rejected(self):
        """Reject inconsistent maps rather than silently counting bytes twice."""
        text, sections = fixture()
        sections = {name: value for name, value in sections.items() if name.endswith(".at_mram")}
        for replacement in ("0x80001008", "0x80002000"):
            with self.subTest(address=replacement), self.assertRaises(ValueError):
                flash.parse_map(text.replace("0x80001010", replacement), sections)


if __name__ == "__main__":
    unittest.main()
