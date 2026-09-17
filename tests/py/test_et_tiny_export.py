# SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates
# <open-source-office@arm.com>
# SPDX-License-Identifier: Apache-2.0
"""Check imported model identity, native fixtures and variable validation counts."""

import hashlib
import importlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from zipfile import ZipFile

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/py"))
importer = importlib.import_module("import_et_tiny_bundle")
builder = importlib.import_module("build_et_tiny")


class EtExportTests(unittest.TestCase):
    """Reject incomplete exports and preserve the reference identity through generation."""

    def test_verified_zip_inventory(self):
        """Only accept archives whose checksum inventory covers their files."""
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            archive = folder / "export.zip"
            data = b"model"
            digest = hashlib.sha256(data).hexdigest()
            for extra in (False, True):
                with ZipFile(archive, "w") as stream:
                    stream.writestr("export/model.pte", data)
                    stream.writestr("export/SHA256SUMS", f"{digest}  model.pte\n")
                    if extra:
                        stream.writestr("export/unlisted.txt", "extra")
                if extra:
                    with self.assertRaises(ValueError):
                        importer.unpack_verified(archive, folder / "invalid")
                else:
                    root = importer.unpack_verified(archive, folder / "valid")
                    self.assertEqual((root / "model.pte").read_bytes(), data)

    def test_native_example_import(self):
        """Keep PTE bytes and signed input/output values unchanged during normalization."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, output = root / "source", root / "normalized"
            source.mkdir()
            output.mkdir()
            pte = source / "test.pte"
            pte.write_bytes(b"example PTE")
            (source / "test.input.int8.bin").write_bytes(bytes([128, 255, 127]))
            (source / "test.output.int8.bin").write_bytes(bytes([254]))
            model = {"pte": "test.pte", "bytes": pte.stat().st_size,
                     "sha256": hashlib.sha256(pte.read_bytes()).hexdigest(),
                     "input": {"dtype": "int8", "shape": [1, 3]},
                     "output": {"dtype": "int8", "shape": [1, 1]}}
            imported = importer.import_model(source, output, "test", model)
            self.assertEqual(imported["validation_samples"], 1)
            self.assertEqual((output / "test.pte").read_bytes(), pte.read_bytes())
            actual = np.load(output / "test.validation_inputs.npy", allow_pickle=False)
            np.testing.assert_array_equal(actual, [[[-128, -1, 127]]])
            model["sha256"] = "0" * 64
            with self.assertRaises(ValueError):
                importer.import_model(source, output, "test", model)

    def test_header_counts_and_reference(self):
        """Generate one or three pairs and reject mismatched input/output sample counts."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "manifest.json").write_text(json.dumps(
                {"validation_reference": "cortex_m_native_int8"}
            ), encoding="utf-8")
            for count in (1, 3):
                for kind in ("inputs", "outputs"):
                    np.save(root / f"test.validation_{kind}.npy",
                            np.zeros((count, 1, 4), dtype=np.int8))
                result = builder.validation_header(root, "test", root / "test.hpp")
                self.assertEqual(result, {"validation_fixture_bytes": count * 8,
                                          "validation_samples": count,
                                          "validation_reference": "cortex_m_native_int8"})
                self.assertIn('"cortex_m_native_int8"',
                              (root / "test.hpp").read_text(encoding="utf-8"))
            np.save(root / "test.validation_outputs.npy", np.zeros((2, 1, 4), dtype=np.int8))
            with self.assertRaises(ValueError):
                builder.validation_header(root, "test", root / "invalid.hpp")


if __name__ == "__main__":
    unittest.main()
