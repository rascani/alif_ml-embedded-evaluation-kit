# SPDX-FileCopyrightText: Copyright 2026 Arm Limited and/or its affiliates
# <open-source-office@arm.com>
# SPDX-License-Identifier: Apache-2.0
"""Paired size/latency build settings and auditable compiler/flash accounting."""

from collections import Counter, defaultdict
import argparse
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess

from tflm_tiny_flash import analyze_model


def prepare_bundle(root: Path, args: argparse.Namespace) -> Path:
    """Create a new bundle without overwriting an earlier experiment.

    :param root:    Repository root.
    :param args:    Bundle name and paired-profile switch.
    :returns:       Newly created bundle directory.
    """
    bundle = root / args.bundle_name
    bundle.mkdir()
    (bundle / "validation").mkdir()
    if args.paired_profiles:
        (bundle / "size").mkdir()
    return bundle


def profile_manifest(bundle: Path, paired: bool) -> dict:
    """Describe the two profiles and the expected UART firmware identity.

    :param bundle:  Bundle directory, also identifying this experiment.
    :param paired:  Whether both optimization profiles are being built.
    :returns:       Additional top-level manifest fields.
    """
    if not paired:
        return {}
    return {
        "build_id": f"{bundle.name}-latency",
        "profiles": {
            "latency": {"logging": True, "optimization": "-Oz", "cmsis": "-O3"},
            "size": {"logging": False, "optimization": "-Oz", "cmsis": "-O3"},
        },
    }


def package_profile_docs(root: Path, bundle: Path, manifest: dict):
    """Include the profile report and its directly referenced supporting documents.

    :param root:        Repository root.
    :param bundle:      Artifact directory before checksumming and packaging.
    :param manifest:    Experiment configuration selecting the matching report.
    """
    reference = bundle / "reference"
    reference.mkdir()
    shutil.copy2(root / "dependencies/cmsis-nn/README.md", reference / "CMSIS-NN-README.md")
    shutil.copy2(root / "docs/e8_tiny_current_summary.md", reference)
    results = bundle / "results"
    results.mkdir()
    report = "e8-tiny-oz-profiles-2026-09-17"
    guide = "e8_tiny_optimized_builds.md"
    if manifest.get("tflm_int8_selection"):
        report = "e8-tflm-int8-registration-2026-09-17"
        guide = "e8_tflm_int8_registration_results.md"
    if manifest.get("profile_documentation"):
        report = manifest["profile_documentation"]["report"]
        guide = manifest["profile_documentation"]["guide"]
    for suffix in ("csv", "json"):
        shutil.copy2(root / f"docs/results/{report}.{suffix}", results)
    text = (root / "docs" / guide).read_text(encoding="utf-8")
    text = text.replace("../dependencies/cmsis-nn/README.md", "reference/CMSIS-NN-README.md")
    text = text.replace("(e8_tiny_current_summary.md)", "(reference/e8_tiny_current_summary.md)")
    (bundle / "README.md").write_text(text, encoding="utf-8")


def profile_options(
    logging: bool, build_id: str, framework: str = "TensorFlowLiteMicro"
) -> list[str]:
    """Keep CMSIS kernels at O3 while compiling the application and runtimes at Oz.

    :param logging:     Enable UART capture in the latency image.
    :param build_id:    Identity required by the host capture parser.
    :param framework:   Framework-specific CMake options to override.
    :returns:           CMake overrides appended after normal benchmark options.
    """
    enabled = "ON" if logging else "OFF"
    options = [
        "-DCMAKE_C_FLAGS_RELEASE=-Oz -g -DNDEBUG",
        "-DCMAKE_CXX_FLAGS_RELEASE=-Oz -g -DNDEBUG",
        "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON",
        "-DCMSIS_DSP_OPTIMIZATION_LEVEL=-O3",
        f"-DMLEK_LOG_ENABLE={enabled}",
        f"-DHAL_LOG_ENABLE={enabled}",
        f"-Dinference_runner_BUILD_ID={build_id}",
    ]
    if framework == "ExecuTorch":
        return options + ["-DEXECUTORCH_OPTIMIZE_SIZE=OFF"]
    return options + [
        "-DTFLM_OPTIMIZATION_LEVEL=-Oz",
        "-DTFLM_OPTIMIZE_KERNELS_FOR=speed",
        "-DTFLM_BUILD_TYPE=release_with_logs",
    ]


def audit_flags(build: Path, output: Path, logging: bool) -> dict:
    """Verify effective compiler flags, including overrides after release flags.

    :param build:       Configured CMake build tree.
    :param output:      Per-image artifact directory.
    :param logging:     Expected framework logging state.
    :returns:           Counts of checked translation units and effective flags.
    :raises ValueError: If optimization, sections, builtins or logging differ.
    """
    commands = json.loads((build / "compile_commands.json").read_text(encoding="utf-8"))
    counts = Counter()
    records = []
    for row in commands:
        source = row["file"]
        if Path(source).suffix not in (".cc", ".cpp", ".c"):
            continue
        args = shlex.split(row["command"])
        cmsis = "/cmsis-nn/" in source or "/cmsis-dsp/" in source
        expected = "-O3" if cmsis else "-Oz"
        levels = [arg for arg in args if re.fullmatch(r"-O(?:[0-3sgz]|fast)", arg)]
        sections = [arg for arg in args if arg in ("-ffunction-sections", "-fno-function-sections")]
        if not levels or levels[-1] != expected or sections[-1:] != ["-ffunction-sections"]:
            raise ValueError(f"Unexpected optimization or function sections: {source}: {args}")
        if cmsis and ("-fno-builtin" in args or "-ffreestanding" in args):
            raise ValueError(f"CMSIS builtins disabled: {source}")
        if "/executorch/runtime/" in source:
            # Upstream log.h defaults to 1; its CMake only defines the disabled value.
            log_flags = [
                arg.split("=", 1)[1] for arg in args if arg.startswith("-DET_LOG_ENABLED=")
            ]
            if (log_flags[-1:] or ["1"]) != [str(int(logging))]:
                raise ValueError(f"Unexpected ExecuTorch logging: {source}")
        if source.endswith("/inference_runner/src/MainLoop.cc"):
            if ("-DMLEK_LOG_ENABLE" in args) != logging:
                raise ValueError("Unexpected runner logging state")
        if "/tensorflow/" in source:
            if ("-DTF_LITE_STRIP_ERROR_STRINGS" in args) == logging:
                raise ValueError(f"Unexpected TFLM logging: {source}")
            if "-DKERNELS_OPTIMIZED_FOR_SPEED" not in args:
                raise ValueError(f"TFLM speed kernel implementation disabled: {source}")
        counts["cmsis_O3" if cmsis else "other_Oz"] += 1
        records.append({"source": source, "optimization": levels[-1], "command": row["command"]})
    if not counts["cmsis_O3"] or not counts["other_Oz"]:
        raise ValueError("Missing CMSIS or runtime compilation commands")
    report = {"logging": logging, "function_sections": True, "counts": dict(counts)}
    (output / "compiler-audit.json").write_text(
        json.dumps({**report, "translation_units": records}, indent=2) + "\n", encoding="utf-8"
    )
    return report


def tflm_sources(build: Path) -> dict:
    """Map archive members and input sections to core/operator source categories.

    :param build:       CMake build with its object files and compilation database.
    :returns:           Categories by member, refined by section for duplicate basenames.
    """
    commands = json.loads((build / "compile_commands.json").read_text(encoding="utf-8"))
    members = defaultdict(list)
    for row in commands:
        if "CMakeFiles/tflu.dir/" in row["command"]:
            members[Path(row["file"]).name + ".obj"].append(row)
    ownership = {}
    for member, rows in members.items():
        sections = defaultdict(set)
        for row in rows:
            group = "kernels" if "/kernels/" in row["file"] else "tflm_core"
            sections["*"].add(group)
            if len(rows) > 1:
                args = shlex.split(row["command"])
                obj = build / args[args.index("-o") + 1]
                objdump = Path(args[0]).with_name("arm-none-eabi-objdump")
                header = subprocess.check_output([str(objdump), "-h", str(obj)], text=True)
                for name in re.findall(r"^\s*\d+\s+(\S+)\s+[0-9a-f]+", header, re.MULTILINE):
                    sections[name].add(group)
        ownership[member] = sections
    return ownership


def tflm_attribution(build: Path, folder: Path, model: dict) -> dict:
    """Split TFLM core/operators by compiled source paths, preserving map byte counts.

    :param build:       CMake compile database for this image.
    :param folder:      Per-image firmware and map directory.
    :param model:       Model and image identity.
    :returns:           Flash fields with the same meaning as the ET manifest fields.
    :raises ValueError: If a retained TFLM member has ambiguous source ownership.
    """
    summary, details = analyze_model(folder, model)
    members = tflm_sources(build)
    groups = Counter()
    for row in details:
        if row["category"] == "tflm":
            member = row["owner"].partition("(")[2].removesuffix(")")
            owners = members[member].get(row["input_section"], members[member]["*"])
            if len(owners) != 1:
                raise ValueError(f"Ambiguous TFLM input section: {member}: {row['input_section']}")
            row["category"] = next(iter(owners))
        groups[row["category"]] += row["size"]
    (folder / "memory-attribution.json").write_text(
        json.dumps({"summary": summary, "flash": dict(groups), "flash_contributions": details},
                   indent=2) + "\n", encoding="utf-8"
    )
    return {
        "flash_runtime_filtered_bytes": summary["filtered_runtime_bytes"],
        "flash_model_plus_runtime_bytes": summary["filtered_model_runtime_bytes"],
        "flash_tflm_core_bytes": groups["tflm_core"],
        "flash_kernels_bytes": groups["kernels"],
        "flash_cmsis_nn_bytes": groups["cmsis_nn"],
        "flash_registry_bytes": groups["selected_resolver"],
        "flash_shared_merged_strings_bytes": groups["shared_merged_strings"],
    }


def audit_int8_registrations(folder: Path) -> dict:
    """Require specialized registrations to be linked, with generic counterparts absent.

    :param folder:      E8 artifact directory with selection metadata and ELF symbols.
    :returns:           Registration policy and verified specialized operator count.
    :raises ValueError: If a selected registration is missing or its generic variant is linked.
    """
    selection = json.loads((folder / "selected_tflm_operators.json").read_text(encoding="utf-8"))
    symbols = (folder / "symbols.txt").read_text(encoding="utf-8")
    specialized = []
    for operator in selection["operators"]:
        registration = operator.get("registration")
        if not registration:
            continue
        if (f"tflite::{registration}()" not in symbols or
                f"tflite::Register_{operator['builtin']}()" in symbols):
            raise ValueError(f"Unexpected linked registrations for {operator['builtin']}")
        specialized.append(operator["builtin"])
    return {
        "operator_registration_policy": (
            "cmsis_nn_int8_when_compatible"
            if selection.get("int8_selection_enabled") else "generic"
        ),
        "int8_registered_operators": specialized,
    }


def record_pair(bundle: Path, model_id: str, latency: dict, size: dict):
    """Attach clearly scoped logging-off sizes without replacing latency-image metadata.

    :param bundle:      Output bundle root.
    :param model_id:    Model subdirectory name.
    :param latency:     Logging-on metadata updated in place.
    :param size:        Logging-off image metadata.
    """
    size["artifact_directory"] = f"size/{model_id}"
    latency["size_build"] = size
    for key, value in size.items():
        if key.startswith("flash_"):
            latency[f"flash_size_build_{key.removeprefix('flash_')}"] = value
    (bundle / "size" / model_id / "metadata.json").write_text(
        json.dumps(size, indent=2) + "\n", encoding="utf-8"
    )
