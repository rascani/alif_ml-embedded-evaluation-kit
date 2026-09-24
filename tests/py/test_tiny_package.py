# SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates
# <open-source-office@arm.com>
# SPDX-License-Identifier: Apache-2.0
"""Verify standalone packages without archived reports or local agent notes."""

import contextlib
import importlib
import io
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/py"))
builder = importlib.import_module("build_tflm_tiny")
board = importlib.import_module("tflm_tiny_board")
profiles = importlib.import_module("tiny_build_profiles")


def prepare_root(root: Path):
    """Create a source fixture with maintained docs but no historical reports.

    :param root:    Temporary repository directory.
    """
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    for name in ("e8_tiny_build_run.md", "e8_tiny_methodology.md", "e8_timer_validation.md"):
        dest = root / "docs" / name
        dest.parent.mkdir(exist_ok=True)
        shutil.copy2(ROOT / "docs" / name, dest)
    for name in ("tflm_tiny_board.py", "tflm_tiny_results.py"):
        dest = root / "scripts/py" / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / "scripts/py" / name, dest)
    for name in ("dependencies/cmsis-nn/README.md",
                 "resources_downloaded/tflm_tiny/LICENSE.mlcommons.md",
                 "resources_downloaded/tflm_tiny/LICENSE.anomaly_detection"):
        dest = root / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text("Fixture attribution\n", encoding="utf-8")
    (root / "build-artifacts").mkdir()
    (root / "source").mkdir()
    (root / "source/new.cc").write_text("// New source fixture\n", encoding="utf-8")
    (root / "docs/local-handoff.md").write_text("Local agent note\n", encoding="utf-8")
    (root / "local-backup.tar.gz").write_bytes(b"Local backup")


class TinyPackageTests(unittest.TestCase):
    """Exercise both frameworks and profiles through archive creation and verification."""

    def test_packages_use_current_docs_without_copying_local_notes(self):
        """Keep packages usable after culling and preserve source provenance boundaries."""
        for framework in ("ExecuTorch", "TensorFlowLiteMicro"):
            for paired in (False, True):
                with self.subTest(framework=framework, paired=paired):
                    with tempfile.TemporaryDirectory() as directory:
                        root = Path(directory)
                        prepare_root(root)
                        bundle = root / "build-test"
                        (bundle / "kws").mkdir(parents=True)
                        (bundle / "kws/mram.bin").write_bytes(b"firmware")
                        manifest = {
                            "models": {"kws": {"flash_total_bytes": 8, "bytes": 8,
                                               "sha256": builder.sha256(bundle / "kws/mram.bin")}},
                            **profiles.profile_manifest(bundle, paired),
                        }
                        if framework == "ExecuTorch":
                            manifest["framework"] = framework
                        else:
                            manifest["tflm_int8_selection"] = True
                        with contextlib.redirect_stdout(io.StringIO()):
                            builder.package(root, bundle, manifest)
                        self.assertEqual(board.verify_bundle(bundle), manifest)
                        self.assertTrue((bundle / "new-source-files/source/new.cc").is_file())
                        names = [str(path.relative_to(bundle)) for path in bundle.rglob("*")]
                        self.assertFalse(any("local-handoff" in name for name in names))
                        self.assertFalse(any("local-backup" in name for name in names))
                        self.assertFalse((bundle / "results").exists())
                        self.assertFalse((bundle / "reference/e8_tiny_current_summary.md").exists())
                        if framework != "ExecuTorch":
                            self.assertTrue((bundle / "LICENSE.mlcommons.md").is_file())
                            self.assertTrue((bundle / "LICENSE.anomaly_detection").is_file())
                        for name in ("README.md", "reference/e8_tiny_methodology.md",
                                     "reference/e8_timer_validation.md"):
                            document = bundle / name
                            for target in re.findall(r"\]\(([^)]+)\)", document.read_text()):
                                if "://" not in target and not target.startswith("#"):
                                    self.assertTrue(
                                        (document.parent / target.split("#")[0]).is_file(), target
                                    )
                        archive = root / "build-artifacts/build-test.tar.gz"
                        extracted = root / "extracted"
                        with tarfile.open(archive) as stream:
                            stream.extractall(extracted, filter="data")
                        result = subprocess.run(
                            [sys.executable, "run.py", "verify"], cwd=extracted / bundle.name,
                            check=True, capture_output=True, text=True,
                        )
                        self.assertIn("Bundle checksums OK", result.stdout)
                        self.assertEqual(
                            json.loads((extracted / bundle.name / "manifest.json").read_text()),
                            manifest,
                        )


if __name__ == "__main__":
    unittest.main()
