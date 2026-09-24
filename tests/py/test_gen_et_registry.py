# SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates
# <open-source-office@arm.com>
# SPDX-License-Identifier: Apache-2.0
"""Tests for capacity calculation when ExecuTorch primitives are selected."""

import tempfile
import unittest
from pathlib import Path

import yaml

from mlek_tools.gen.gen_et_registry import generate_registry_header


class RegistryGenerationTests(unittest.TestCase):
    """Check variant counts, primitives, empty graphs, and wildcard rejection."""

    def test_variants_primitives_and_model_replacement(self):
        """Count a primitive once and update capacity when the model changes."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            oplist, header = root / "ops.yaml", root / "registry.h"
            selection = {
                "operators": {"aten::add.out": {}, "executorch_prim::et_view.default": {}},
                "et_kernel_metadata": {"aten::add.out": ["key1", "key2", "key1"],
                                       "cortex_m::quantize_per_tensor.out": ["key3"]},
            }
            oplist.write_text(yaml.safe_dump(selection), encoding="utf-8")
            self.assertEqual(generate_registry_header(oplist, header), 4)
            self.assertIn("EXECUTORCH_SELECTED_MAX_KERNEL_NUM 4", header.read_text())
            oplist.write_text("{}", encoding="utf-8")
            self.assertEqual(generate_registry_header(oplist, header), 1)
            self.assertIn("EXECUTORCH_SELECTED_MAX_KERNEL_NUM 1", header.read_text())

    def test_wildcards_are_rejected(self):
        """Refuse a capacity estimate when the operator list is open-ended."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for selection in [
                {"include_all_operators": True},
                {"operators": {"aten::add": {"include_all_overloads": True}}},
            ]:
                with self.subTest(selection=selection):
                    oplist = root / "ops.yaml"
                    oplist.write_text(yaml.safe_dump(selection), encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, "explicit operators"):
                        generate_registry_header(oplist, root / "registry.h")


if __name__ == "__main__":
    unittest.main()
