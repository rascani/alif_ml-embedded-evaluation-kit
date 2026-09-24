# SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates
# <open-source-office@arm.com>
# SPDX-License-Identifier: Apache-2.0
"""Check Tiny bundle capture, programming order, and measurement accounting."""

import argparse
import contextlib
import hashlib
import importlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/py"))
board = importlib.import_module("tflm_tiny_board")
results = importlib.import_module("tflm_tiny_results")


def fixture() -> tuple[dict, str]:
    """Return a short complete run with independently specified expected statistics."""
    manifest = {
        "models": {
            "kws": {
                "sha256": "abc",
                "bytes": 123,
                "flash_total_bytes": 1000,
                "flash_model_bytes": 123,
                "flash_non_model_bytes": 877,
            }
        },
        "benchmark": {"warmups": 2, "measurements": 3},
    }
    text = """INFO - Processor internal clock: 400000000Hz
INFO - BENCHMARK model id=kws sha256=abc bytes=123
INFO - Total number of inferences: 6
INFO - BENCHMARK config version=1 input=synthetic_v1 warmups=2 measured=3
INFO - BENCHMARK first value=8000 unit=cycles
INFO - BENCHMARK sample index=0 value=400 unit=cycles
INFO - BENCHMARK sample index=1 value=1200 unit=cycles
INFO - BENCHMARK sample index=2 value=800 unit=cycles
INFO - BENCHMARK summary count=3 min=400 mean=800.000 median=800.000 max=1200 p95=1200 unit=cycles
INFO - MEMORY arena reserved=4096 head=1000 persistent=200 init_peak=2000 invoke_peak=1200 peak=2000 audit_overhead=32 raw_peak=2032 invoke_allocation_calls=0
INFO - MEMORY outside model_object=100 init_heap_delta=300 interpreter_object=200 persistent=400
INFO - MEMORY total inference_peak=1600 lifecycle_arena_plus_persistent=2400
INFO - Inference completed.
INFO - program terminating...
"""
    return manifest, text


class TinyResultsTests(unittest.TestCase):
    """Reject wrong and incomplete measurements while preserving raw samples."""

    def test_statistics_and_ram(self):
        """Check clock conversion and count the arena tail and interpreter only once."""
        manifest, text = fixture()
        row = results.parse_boot(text, manifest, "kws")
        self.assertEqual(row["mean_us"], 2)
        self.assertEqual(row["first_us"], 20)
        self.assertEqual(row["p95_us"], 3)
        self.assertEqual(row["ram_inference_peak_bytes"], 1600)
        self.assertEqual(row["samples_cycles"], [400, 1200, 800])
        self.assertEqual(row["flash_total_bytes"], 1000)

    def test_reject_corrupted_or_wrong_runs(self):
        """Missing samples, wrong models, bad summaries, and double counts must fail."""
        manifest, text = fixture()
        for before, after in (
            ("index=1", "index=2"),
            ("mean=800.000", "mean=900.000"),
            ("mean=800.000", "mean=nan"),
            ("sha256=abc", "sha256=def"),
            ("id=kws", "id=ic"),
            ("inference_peak=1600", "inference_peak=1800"),
            ("unit=cycles", "unit=microseconds"),
            ("Inference completed.", "Inference failed."),
        ):
            with self.subTest(before=before), self.assertRaises(ValueError):
                results.parse_boot(text.replace(before, after), manifest, "kws")

    def test_build_identity_rejects_old_firmware_with_same_model(self):
        """Require the new profile's identity even when model weights have not changed."""
        manifest, text = fixture()
        manifest["build_id"] = "oz-latency-v2"
        record = "INFO - BENCHMARK build id=oz-latency-v2\n"
        parsed = results.parse_boot(record + text, manifest)
        self.assertEqual(parsed["build_id"], manifest["build_id"])
        for invalid in (text, record.replace("v2", "v1") + text, record * 2 + text):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                results.parse_boot(invalid, manifest)

    def test_multiple_boots_and_output(self):
        """Retain every boot and raw sample; reject an incomplete trailing capture."""
        manifest, text = fixture()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "uart.log"
            path.write_text(text * 3, encoding="utf-8")
            rows = results.read_logs([path], manifest)
            self.assertEqual(len(rows), 3)
            self.assertEqual(rows[-1]["boot"], 3)
            output = Path(directory) / "results.csv"
            results.write_results(rows, output)
            self.assertIn("ram_inference_peak_bytes", output.read_text(encoding="utf-8"))
            self.assertEqual(len(json.loads(output.with_suffix(".json").read_text())), 3)
            path.write_text(text + "INFO - new boot", encoding="utf-8")
            with self.assertRaises(ValueError):
                results.read_logs([path], manifest)


class TinyFlashTests(unittest.TestCase):
    """Exercise SE Tools orchestration without opening any hardware connection."""

    def test_generation_failure_never_writes_mram(self):
        """Preserve DEVICE metadata and stop before programming if packaging fails."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "kws").mkdir()
            (root / "kws/mram.bin").write_bytes(b"firmware")
            tools_dir = root / "tools"
            (tools_dir / "build/config").mkdir(parents=True)
            (tools_dir / "build/images").mkdir()
            device = {"binary": "custom-device.json", "signed": True, "version": "0.5.00"}
            (tools_dir / "build/config/app-cfg.json").write_text(json.dumps({"DEVICE": device}))
            with patch("tflm_tiny_board.subprocess.run") as run:
                run.side_effect = subprocess.CalledProcessError(1, "app-gen-toc")
                with self.assertRaises(subprocess.CalledProcessError):
                    board.flash_model(root, "kws", tools_dir, "/dev/test")
                self.assertEqual(run.call_count, 1)
            config = json.loads((tools_dir / "build/config/e8-tiny-kws.json").read_text())
            self.assertEqual(config["DEVICE"], device)
            self.assertEqual(config["HP_Tiny"]["cpu_id"], "M55_HP")
            self.assertEqual(config["HP_Tiny"]["flags"], ["boot"])
            with patch("tflm_tiny_board.subprocess.run") as run:
                board.flash_model(root, "kws", tools_dir, "/dev/test")
                self.assertEqual(run.call_count, 2)
                self.assertEqual(run.call_args.args[0][-3:], ["-c", "/dev/test", "-p"])

    def test_checksum_tampering(self):
        """Reject changed metadata before invoking any vendor tool."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            content = b'{"models": {}}'
            (root / "manifest.json").write_bytes(content)
            digest = hashlib.sha256(content).hexdigest()
            (root / "SHA256SUMS").write_text(f"{digest}  manifest.json\n")
            self.assertEqual(board.verify_bundle(root), {"models": {}})
            (root / "manifest.json").write_bytes(b"tampered")
            with self.assertRaises(ValueError):
                board.verify_bundle(root)


class FakeUart:
    """Serial fixture yielding fragmented input across record boundaries."""

    def __init__(self, data: bytes):
        """Store the UART stream.

        :param data:    Bytes to deliver.
        """
        self.data = data
        self.in_waiting = 7

    def __enter__(self) -> "FakeUart":
        """Return the persistent port handle."""
        return self

    def __exit__(self, *_args: object):
        """Close the simulated handle."""

    def read(self, count: int) -> bytes:
        """Return the next fragment.

        :param count:   Maximum bytes to read.
        :returns:       Next byte fragment.
        """
        result, self.data = self.data[:count], self.data[count:]
        return result


class Console(io.StringIO):
    """Console accepting the same binary display writes as a real terminal."""

    def __init__(self):
        """Create independent text and binary sinks."""
        super().__init__()
        self.buffer = io.BytesIO()


class TinyCaptureTests(unittest.TestCase):
    """Check auto-stop and raw byte preservation across fragmented UART reads."""

    def test_capture_three_boots(self):
        """Capture complete boots once, using the explicit port settings."""
        manifest, text = fixture()
        data = b"\xff" + text.encode() * 3
        module = SimpleNamespace(EIGHTBITS=8, PARITY_NONE="N", STOPBITS_ONE=1)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = argparse.Namespace(logs=None, port="test", boots=3, timeout=5)
            with patch(
                "tflm_tiny_board.importlib.import_module", return_value=module
            ), patch.object(
                module, "Serial", create=True, return_value=FakeUart(data)
            ) as serial, contextlib.redirect_stdout(
                Console()
            ):
                output = board.capture_model(root, "kws", manifest, args)
            serial.assert_called_once()
            self.assertEqual(serial.call_args.kwargs["rtscts"], False)
            self.assertEqual(serial.call_args.kwargs["xonxoff"], False)
            captured = output.read_bytes()
            self.assertTrue(data.startswith(captured))
            self.assertEqual(len(results.read_logs([output], manifest)), 3)


if __name__ == "__main__":
    unittest.main()
