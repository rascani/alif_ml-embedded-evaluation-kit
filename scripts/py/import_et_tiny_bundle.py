#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates
# <open-source-office@arm.com>
# SPDX-License-Identifier: Apache-2.0
"""Freeze a trained Tiny export ZIP and its supplied native validation examples."""

import argparse
import json
from pathlib import Path, PurePosixPath
import shutil
from zipfile import ZipFile

import numpy as np

from build_et_tiny import MODELS
from build_tflm_tiny import sha256


def unpack_verified(archive: Path, output: Path) -> Path:
    """Extract a single-root bundle, checking its complete checksum inventory.

    :param archive:     Export ZIP supplied by the model producer.
    :param output:      New destination directory.
    :returns:           Verified extracted root.
    :raises ValueError: If paths or checksums are inconsistent.
    """
    with ZipFile(archive) as stream:
        names = [PurePosixPath(name) for name in stream.namelist()]
        if (len({name.parts[0] for name in names}) != 1 or
                any(name.is_absolute() or ".." in name.parts for name in names)):
            raise ValueError("Expected one relative ZIP root without parent traversal")
        stream.extractall(output)
    root = output / names[0].parts[0]
    listed = set()
    for line in (root / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        digest, name = line.split("  ", 1)
        path = (root / name).resolve()
        if not path.is_relative_to(root.resolve()) or sha256(path) != digest or name in listed:
            raise ValueError(f"Export checksum/path mismatch: {name}")
        listed.add(name)
    actual = {str(path.relative_to(root)) for path in root.rglob("*") if path.is_file()}
    if actual != listed | {"SHA256SUMS"}:
        raise ValueError("Export checksum inventory does not cover every file")
    return root


def import_model(source: Path, output: Path, name: str, metadata: dict) -> dict:
    """Copy an unchanged PTE and convert its native example pair to runner fixtures.

    :param source:      Verified source bundle root.
    :param output:      Normalized export directory.
    :param name:        Export model name.
    :param metadata:    Model contract from the verified manifest.
    :returns:           Model metadata with fixture provenance.
    :raises ValueError: If the PTE identity or example tensor size is inconsistent.
    """
    pte = (source / metadata["pte"]).resolve()
    if (not pte.is_relative_to(source.resolve()) or sha256(pte) != metadata["sha256"] or
            pte.stat().st_size != metadata["bytes"]):
        raise ValueError(f"PTE identity mismatch: {name}")
    shutil.copy2(pte, output / f"{name}.pte")
    fixtures = {}
    for kind in ("input", "output"):
        contract = metadata[kind]
        binary = pte.with_name(f"{name}.{kind}.int8.bin")
        shape = contract["shape"]
        if contract["dtype"] != "int8" or binary.stat().st_size != int(np.prod(shape)):
            raise ValueError(f"Invalid native example {kind}: {name}")
        values = np.fromfile(binary, dtype=np.int8).reshape((1, *shape))
        fixture = output / f"{name}.validation_{kind}s.npy"
        np.save(fixture, values, allow_pickle=False)
        fixtures[kind] = {"source": str(binary.relative_to(source.resolve())),
                          "binary_sha256": sha256(binary), "npy_sha256": sha256(fixture)}
    return dict(metadata, pte=f"{name}.pte", validation_samples=1,
                validation_reference="cortex_m_native_int8", validation_examples=fixtures)


def main():
    """Import the archive without modifying the producer's files or earlier exports."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir()
    source = unpack_verified(args.archive, output / "original")
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    manifest["weights"] = "Trained MLPerf Tiny reference weights; quantization per export manifest"
    manifest["validation_reference"] = "cortex_m_native_int8"
    manifest["source_archive_sha256"] = sha256(args.archive)
    manifest["models"] = {
        name: import_model(source, output, name, manifest["models"][name])
        for name in MODELS.values()
    }
    shutil.copy2(args.archive, output / "source.zip")
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    files = sorted(path for path in output.rglob("*") if path.is_file())
    (output / "SHA256SUMS").write_text(
        "".join(f"{sha256(path)}  {path.relative_to(output)}\n" for path in files), encoding="utf-8"
    )
    print(f"Verified and imported {len(manifest['models'])} models into {output}")


if __name__ == "__main__":
    main()
