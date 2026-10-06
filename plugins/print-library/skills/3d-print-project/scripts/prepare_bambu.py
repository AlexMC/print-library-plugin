#!/usr/bin/env python3
"""Export and verify an unsliced Bambu project using an explicit workshop preset.

Only local export/slice commands are available. Temporary verification toolpaths
are deleted; this helper never submits a print or contacts a printer.

--workshop names either a library's workshop.json (shareable facts, next to
library.json) or a standalone/legacy workshop profile. A library workshop is
merged with local configuration (--local-config, default
~/.config/3d-print/local.json, else the legacy ~/.config/3d-print/workshop.json),
which holds the host paths: slicer executable and preset profile files.
Inside a record folder, library or other repository the receipt names files
by relative path and hash; host details go into verification.local.json and
the raw slicer output into slicer.local.log, both gitignored.
"""
import argparse
from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile

from host_details import LOG_SUFFIX, Locations, host_details, scrub, sidecar_path

LOCAL_CONFIG = Path("~/.config/3d-print/local.json")
LEGACY_PROFILE = Path("~/.config/3d-print/workshop.json")


CORE = "{http://schemas.microsoft.com/3dmanufacturing/core/2015/02}"
PRODUCTION = "{http://schemas.microsoft.com/3dmanufacturing/production/2015/06}"
IDENTITY = "1 0 0 0 1 0 0 0 1 0 0 0"
PLACEMENT_TOLERANCE_MM = 0.0001
COMMAND_TIMEOUT_SECONDS = 300
NUMBER = r"[-+]?(?:(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?|nan|inf(?:inity)?)"
ARGUMENT = re.compile(r"([A-Za-z])(" + NUMBER + r")", re.IGNORECASE)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path):
    def reject_constant(value):
        raise ValueError("Nonfinite JSON value: " + value)
    value = json.loads(path.read_text(encoding="utf-8"), parse_constant=reject_constant)
    require(isinstance(value, dict), "Expected a JSON object: " + str(path))
    return value


def file_path(value, base, label):
    require(isinstance(value, str) and bool(value), label + " must be a file path")
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base / path
    path = path.resolve(strict=True)
    require(path.is_file(), label + " is not a file: " + str(path))
    return path


def load_workshop(workshop_path, local_override):
    """(host profile path, host profile, library workshop facts or None).

    Outside a library the workshop file is itself the host profile, as before.
    In a library, workshop.json holds only shareable facts; the presets and
    software paths come from local configuration.
    """
    workshop = load_json(workshop_path)
    require(type(workshop.get("schema_version")) is int and workshop["schema_version"] == 1,
            "Unsupported workshop schema_version; expected 1")
    if not (workshop_path.parent / "library.json").is_file():
        require(local_override is None, "--local-config applies only to a library's workshop.json")
        return workshop_path, workshop, None
    for key in ("presets", "software"):
        require(key not in workshop, "The library workshop.json must not hold '" + key +
                "'; host paths and preset files belong in local configuration")
    if local_override is not None:
        local = local_override.expanduser().resolve(strict=True)
    else:
        found = [path.expanduser() for path in (LOCAL_CONFIG, LEGACY_PROFILE) if path.expanduser().is_file()]
        require(bool(found), "No local configuration: create " + str(LOCAL_CONFIG) +
                " from templates/local.example.json or pass --local-config")
        local = found[0].resolve(strict=True)
    profile = load_json(local)
    require(type(profile.get("schema_version")) is int and profile["schema_version"] == 1,
            "Unsupported local configuration schema_version; expected 1")
    return local, profile, workshop


def load_preset(profile_path, profile, preset_id, override, library):
    slicer = (library or {}).get("slicer", {})
    listed = slicer.get("preset_ids") if isinstance(slicer, dict) else None
    if library is not None and isinstance(listed, list) and listed:
        require(preset_id in listed, "Preset " + preset_id + " is not listed in the library workshop.json slicer.preset_ids")
    presets = profile.get("presets")
    require(isinstance(presets, dict) and preset_id in presets,
            "Unknown explicit preset: " + preset_id)
    preset = presets[preset_id]
    require(isinstance(preset, dict), "Preset must be a JSON object")
    profiles = {key: file_path(preset.get(key), profile_path.parent, key)
                for key in ("machine", "process", "filament")}
    for path in profiles.values():
        load_json(path)
    expected = preset.get("expected_settings")
    require(isinstance(expected, dict) and bool(expected),
            "Preset expected_settings must be a nonempty map")
    volume = preset.get("build_volume_mm")
    require(isinstance(volume, list) and len(volume) == 3 and
            all(type(v) in (int, float) and math.isfinite(v) and v > 0 for v in volume),
            "Preset build_volume_mm must contain three finite positive numbers")
    require(type(preset.get("require_supports")) is bool,
            "Preset require_supports must be a boolean")
    assumptions = preset.get("assumptions")
    require(isinstance(assumptions, list) and all(isinstance(a, str) for a in assumptions),
            "Preset assumptions must be an array of strings")
    if override:
        executable = file_path(override, Path.cwd(), "Slicer")
    else:
        software = profile.get("software", {})
        require(isinstance(software, dict), "Workshop software must be a map")
        bambu = software.get("bambu_studio", {})
        require(isinstance(bambu, dict), "Workshop software.bambu_studio must be a map")
        executable = file_path(bambu.get("path"), profile_path.parent, "Bambu Studio")
    require(os.access(str(executable), os.X_OK), "Slicer is not executable: " + str(executable))
    return preset, profiles, executable


def transform(text):
    values = [float(value) for value in text.split()]
    require(len(values) == 12 and all(math.isfinite(v) for v in values),
            "Invalid/nonfinite model transform")
    rows = [values[i:i + 3] for i in (0, 3, 6)]
    for i in range(3):
        for j in range(3):
            require(abs(sum(a * b for a, b in zip(rows[i], rows[j])) - int(i == j)) < 1e-6,
                    "Model transform contains scaling or shear")
    determinant = (values[0] * (values[4] * values[8] - values[5] * values[7])
                   - values[1] * (values[3] * values[8] - values[5] * values[6])
                   + values[2] * (values[3] * values[7] - values[4] * values[6]))
    require(abs(determinant - 1) < 1e-6, "Model transform contains a reflection")
    require(all(abs(values[i]) < 1e-6 for i in (2, 5, 6, 7)) and abs(values[8] - 1) < 1e-6,
            "Model print orientation changed out of the XY plane")
    return values


def move(vertex, matrix):
    return [sum(vertex[j] * matrix[3 * j + i] for j in range(3)) + matrix[9 + i]
            for i in range(3)]


def metadata(element):
    return {item.attrib["key"]: item.attrib["value"]
            for item in element.findall("metadata") if "key" in item.attrib}


def verify_project(path, source_names, preset):
    with zipfile.ZipFile(path) as archive:
        require(not any(name.lower().endswith((".gcode", ".bgcode")) for name in archive.namelist()),
                "Project contains toolpaths; only unsliced projects may be delivered")
        settings = json.loads(archive.read("Metadata/project_settings.config"))
        for key, expected in preset["expected_settings"].items():
            require(key in settings and settings[key] == expected,
                    "Project setting mismatch for {!r}: expected {!r}, received {!r}".format(
                        key, expected, settings.get(key)))
        roots = {}

        def model_root(name):
            if name not in roots:
                root = ET.fromstring(archive.read(name))
                require(root.attrib.get("unit") == "millimeter", "3MF units must be millimeter")
                resources = root.find(CORE + "resources")
                require(resources is not None, "Missing 3MF resources")
                roots[name] = (root, {obj.attrib["id"]: obj for obj in resources
                                      if obj.tag == CORE + "object"})
            return roots[name]

        def vertices(name, object_id, chain, active):
            key = (name, object_id)
            require(key not in active, "Cyclic 3MF component graph")
            _, resources = model_root(name)
            require(object_id in resources, "Missing referenced 3MF object: " + object_id)
            obj = resources[object_id]
            mesh = obj.find(CORE + "mesh")
            components = obj.find(CORE + "components")
            require((mesh is None) != (components is None), "Expected mesh or components in 3MF object")
            if mesh is not None:
                points = mesh.find(CORE + "vertices")
                require(points is not None, "Missing mesh vertices")
                for vertex in points:
                    point = [float(vertex.attrib[axis]) for axis in ("x", "y", "z")]
                    require(all(math.isfinite(v) for v in point), "Nonfinite mesh vertex")
                    for placement in chain:
                        point = move(point, placement)
                    require(all(math.isfinite(v) for v in point), "Nonfinite placed mesh vertex")
                    yield point
            else:
                for component in components:
                    child = component.attrib.get(PRODUCTION + "path", name).lstrip("/")
                    local = transform(component.attrib.get("transform", IDENTITY))
                    yield from vertices(child, component.attrib["objectid"], [local] + chain, active | {key})

        root, _ = model_root("3D/3dmodel.model")
        build = root.find(CORE + "build")
        require(build is not None, "Missing 3MF build")
        items = list(build)
        require(len(items) == len(source_names), "Exported model count differs from STL input count")
        model_settings = ET.fromstring(archive.read("Metadata/model_settings.config"))
        names = {obj.attrib["id"]: metadata(obj).get("name") for obj in model_settings.findall("object")}
        require(Counter(names.get(item.attrib["objectid"]) for item in items) == Counter(source_names),
                "Exported model names do not match the requested STL inputs")
        plates = model_settings.findall("plate")
        require(len(plates) == 1, "Project must contain exactly one plate")
        placed_ids = [metadata(instance).get("object_id") for instance in plates[0].findall("model_instance")]
        require(Counter(placed_ids) == Counter(item.attrib["objectid"] for item in items),
                "Not every requested model is assigned once to the plate")
        bounds = []
        for item in items:
            require(item.attrib.get("printable", "1") in ("1", "true"), "A model is marked non-printable")
            placement = transform(item.attrib.get("transform", IDENTITY))
            low, high = [math.inf] * 3, [-math.inf] * 3
            count = 0
            for point in vertices("3D/3dmodel.model", item.attrib["objectid"], [placement], set()):
                count += 1
                for axis in range(3):
                    low[axis] = min(low[axis], point[axis])
                    high[axis] = max(high[axis], point[axis])
            require(count > 0, "Model contains no vertices")
            require(abs(low[2]) <= PLACEMENT_TOLERANCE_MM, "Model is not resting on the bed")
            require(all(low[axis] >= -PLACEMENT_TOLERANCE_MM and
                        high[axis] <= preset["build_volume_mm"][axis] + PLACEMENT_TOLERANCE_MM
                        for axis in range(3)), "Model lies outside configured XYZ build volume")
            bounds.append({"name": names[item.attrib["objectid"]], "minimum": low, "maximum": high})
        return {"settings_checked": preset["expected_settings"], "units": "millimeter",
                "objects": len(items), "placed_model_bounds_mm": bounds,
                "proper_rigid_transforms_only": True, "out_of_plane_rotation": False,
                "all_models_on_bed": True, "inside_build_volume": True,
                "build_volume_mm": preset["build_volume_mm"],
                "placement_tolerance_mm": PLACEMENT_TOLERANCE_MM}


def verify_slice(path, source_names, require_supports):
    with zipfile.ZipFile(path) as archive:
        info = ET.fromstring(archive.read("Metadata/slice_info.config"))
        plates = info.findall("plate")
        require(len(plates) == 1, "Verification slice must contain exactly one plate")
        plate = plates[0]
        values = metadata(plate)
        require(values.get("outside") == "false", "Slicer reports geometry outside the build volume")
        require(values.get("support_used") in ("true", "false"), "Missing support usage evidence")
        require(not require_supports or values["support_used"] == "true", "Preset requires support toolpaths")
        objects = plate.findall("object")
        require(len(objects) == len(source_names) and all(obj.attrib.get("skipped") == "false" for obj in objects),
                "Not all requested objects were printed")
        require(Counter(obj.attrib.get("name") for obj in objects) == Counter(source_names),
                "Sliced object names do not match requested STL inputs")
        toolpaths = [name for name in archive.namelist() if name.lower().endswith((".gcode", ".bgcode"))]
        require(toolpaths == ["Metadata/plate_1.gcode"], "Expected exactly one plain-text plate toolpath")
        raw_gcode = archive.read(toolpaths[0])
        gcode = raw_gcode.decode("utf-8")
        extrusion_commands = 0
        for line_number, line in enumerate(gcode.splitlines(), 1):
            command = line.split(";", 1)[0].strip()
            if not command:
                continue
            args = list(ARGUMENT.finditer(command))
            for arg in args:
                require(math.isfinite(float(arg.group(2))),
                        "Nonfinite G-code argument at line " + str(line_number))
            if re.match(r"^G(?:0?[123])(?:\s|[XYZEF])", command, re.IGNORECASE) and any(
                    arg.group(1).upper() == "E" and float(arg.group(2)) > 0 for arg in args):
                extrusion_commands += 1
        require(extrusion_commands > 0, "No positive extrusion toolpaths")
        timing = re.search(r"total estimated time:\s*(?:(\d+)d\s*)?(?:(\d+)h\s*)?"
                           r"(?:(\d+)m\s*)?(\d+)s", gcode)
        require(timing is not None, "Missing total duration in G-code header")
        seconds = sum(int(n or 0) * factor for n, factor in zip(timing.groups(), (86400, 3600, 60, 1)))
        predicted = float(values.get("prediction", "nan"))
        require(seconds > 0 and math.isfinite(predicted) and predicted == seconds,
                "Slice duration does not match G-code total estimated time")
        weight = float(values.get("weight", "nan"))
        require(math.isfinite(weight) and weight > 0, "Missing positive finite filament estimate")
        return {"slice_passed": True, "plates": 1, "objects_printed": len(objects),
                "printed_objects": [dict(obj.attrib) for obj in objects],
                "outside_build_volume": False, "support_used": values["support_used"] == "true",
                "supports_required": require_supports, "total_estimated_seconds": seconds,
                "duration_matches_gcode_header": True, "estimated_filament_g_including_supports_and_brim": weight,
                "finite_numeric_gcode_arguments": True, "positive_extrusion_commands": extrusion_commands,
                "warnings": [dict(warning.attrib) for warning in plate.iter("warning")],
                "first_layer_time_metadata": {"value": values.get("first_layer_time"), "used": False,
                                              "reason": "Known unreliable Bambu CLI metadata; not a timing estimate."},
                "toolpath_bytes": len(raw_gcode), "toolpath_sha256": hashlib.sha256(raw_gcode).hexdigest()}


def run(command, cwd, log, evidence):
    log.write("COMMAND " + json.dumps(command) + "\n")
    log.flush()
    with tempfile.TemporaryFile(mode="w+b") as captured:
        try:
            result = subprocess.run(command, cwd=str(cwd), stdin=subprocess.DEVNULL,
                                    stdout=captured, stderr=subprocess.STDOUT, timeout=COMMAND_TIMEOUT_SECONDS,
                                    check=False)
        except subprocess.TimeoutExpired:
            raise RuntimeError("Slicer exceeded {} second timeout".format(COMMAND_TIMEOUT_SECONDS))
        captured.seek(0)
        output = captured.read().decode("utf-8", errors="replace")
    log.write(output + "\n")
    log.flush()
    evidence.append({"argv": command, "cwd": str(cwd), "returncode": result.returncode,
                     "timeout_seconds": COMMAND_TIMEOUT_SECONDS})
    if result.returncode != 0:
        raise RuntimeError("Slicer failed (exit {}): {}".format(result.returncode, output[-2000:].strip()))
    return [line for line in output.splitlines() if re.search(r"warn(?:ing)?", line, re.IGNORECASE)]


COMMAND_STEPS = ("export", "slice")


def split_report(report, locations, temporary, output):
    """A committed receipt (relative paths, hashes) and the sidecar's host details, from the full report."""
    describe = locations.describe
    hidden = {str(temporary): "<temp>", report["slicer"]["path"]: "<slicer>", str(output): "<output>",
              str(Path.home()): "<home>"}
    receipt = dict(report)
    receipt["workshop"] = dict(describe(report["workshop"]["path"]), sha256=report["workshop"]["sha256"])
    if "local_config" in report:
        receipt["local_config"] = {"name": Path(report["local_config"]["path"]).name,
                                   "sha256": report["local_config"]["sha256"]}
    receipt["profiles"] = {key: dict(describe(value["path"]), sha256=value["sha256"])
                           for key, value in report["profiles"].items()}
    receipt["sources"] = [dict(describe(source["path"]), sha256=source["sha256"], bytes=source["bytes"])
                          for source in report["sources"]]
    receipt["slicer"] = dict(describe(report["slicer"]["path"]), sha256=report["slicer"]["sha256"])
    receipt["commands"] = [{"step": COMMAND_STEPS[i] if i < len(COMMAND_STEPS) else str(i),
                            "returncode": command["returncode"], "timeout_seconds": command["timeout_seconds"]}
                           for i, command in enumerate(report["commands"])]
    receipt["slicer_log_warnings"] = [scrub(line, hidden) for line in report["slicer_log_warnings"]]
    receipt["slicer_log"] = "slicer" + LOG_SUFFIX
    receipt["host_details"] = sidecar_path(output / "verification.json").name
    receipt["paths_note"] = locations.paths_note()
    receipt["notes"] = [note.replace("retained in slicer.log", "retained in the gitignored slicer" + LOG_SUFFIX)
                        for note in report["notes"]]
    details = {"output_dir": str(output),
               "workshop_path": report["workshop"]["path"],
               "local_config_path": report.get("local_config", {}).get("path"),
               "profiles": {key: value["path"] for key, value in report["profiles"].items()},
               "sources": [source["path"] for source in report["sources"]],
               "slicer_path": report["slicer"]["path"],
               "commands": report["commands"]}
    return receipt, details


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workshop", required=True, type=Path,
                        help="The library's workshop.json, or a standalone/legacy workshop profile")
    parser.add_argument("--local-config", type=Path,
                        help="Host-only configuration merged with a library workshop.json (default "
                             + str(LOCAL_CONFIG) + ", else the legacy " + str(LEGACY_PROFILE) + ")")
    parser.add_argument("--preset", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--slicer", help="Explicit local Bambu Studio executable override")
    parser.add_argument("inputs", nargs="+", type=Path, metavar="INPUT.stl")
    args = parser.parse_args()
    workshop_path = args.workshop.expanduser().resolve(strict=True)
    profile_path, profile, library = load_workshop(workshop_path, args.local_config)
    preset, profiles, executable = load_preset(profile_path, profile, args.preset, args.slicer, library)
    sources = [path.expanduser().resolve(strict=True) for path in args.inputs]
    require(all(path.is_file() and path.suffix.lower() == ".stl" for path in sources),
            "All inputs must be existing STL files")
    identities = [(path.stat().st_dev, path.stat().st_ino) for path in sources]
    require(len(set(identities)) == len(sources), "STL inputs must be distinct files, not aliases or hard links")
    require(len({path.stem.casefold() for path in sources}) == len(sources),
            "STL inputs must have distinct stems (case-insensitive)")
    output = args.output_dir.expanduser().absolute()
    require(not os.path.lexists(str(output)), "Output directory already exists: " + str(output))
    require(output.parent.is_dir(), "Output parent directory must already exist: " + str(output.parent))
    output = output.parent.resolve(strict=True) / output.name
    source_names = [path.name for path in sources]
    locations = Locations(output.parent)
    log_name = "slicer" + LOG_SUFFIX if locations.portable else "slicer.log"
    delivered = ("project.3mf", "verification.json", sidecar_path(output / "verification.json").name, log_name) \
        if locations.portable else ("project.3mf", "verification.json", log_name)
    commands, warnings = [], []
    with tempfile.TemporaryDirectory(prefix=".bambu-prepare-", dir=str(output.parent)) as temporary:
        temporary = Path(temporary)
        staged = temporary / "delivery"
        staged.mkdir()
        input_dir = temporary / "inputs"
        input_dir.mkdir()
        profile_dir = temporary / "profiles"
        profile_dir.mkdir()
        source_records = []
        for source in sources:
            target = input_dir / source.name
            shutil.copyfile(str(source), str(target))
            source_records.append({"path": str(source), "sha256": sha256(target), "bytes": target.stat().st_size})
        profile_records = {}
        staged_profiles = {}
        for key, source in profiles.items():
            target = profile_dir / (key + ".json")
            shutil.copyfile(str(source), str(target))
            staged_profiles[key] = target
            profile_records[key] = {"path": str(source), "sha256": sha256(target)}
        base = [str(executable), "--datadir", str(temporary / "settings")]
        project = staged / "project.3mf"
        export = base + ["--load-settings", str(staged_profiles["machine"]) + ";" + str(staged_profiles["process"]),
                         "--load-filaments", str(staged_profiles["filament"]),
                         "--orient", "0", "--arrange", "1", "--ensure-on-bed",
                         "--export-3mf", str(project)] + [str(input_dir / name) for name in source_names]
        verification_dir = temporary / "slice"
        verification_dir.mkdir()
        sliced = verification_dir / "verification_sliced.3mf"
        slice_command = base + ["--slice", "1", "--outputdir", str(verification_dir),
                                "--export-3mf", sliced.name, str(project)]
        with (staged / log_name).open("x", encoding="utf-8") as log:
            warnings.extend(run(export, temporary, log, commands))
            project_result = verify_project(project, source_names, preset)
            warnings.extend(run(slice_command, temporary, log, commands))
            slice_result = verify_slice(sliced, source_names, preset["require_supports"])
        report = {"schema_version": 1, "preset_id": args.preset,
                  "workshop": {"path": str(workshop_path), "sha256": sha256(workshop_path)},
                  "profiles": profile_records, "sources": source_records,
                  "slicer": {"path": str(executable), "sha256": sha256(executable)},
                  "assumptions": preset["assumptions"], "commands": commands,
                  "printer_contacted": False, "delivered_unsliced": True,
                  "verification_toolpaths_discarded": True, "project": project_result,
                  "slice": slice_result, "slicer_log_warnings": warnings,
                  "project_sha256": sha256(project),
                  "notes": ["Only local export and verification slicing were requested; no printer or network commands are exposed.",
                            "Temporary command paths are execution evidence and are deleted after verification.",
                            "All slicer output is retained in slicer.log; warnings are not suppressed.",
                            "First-layer timing metadata is known unreliable and is not used. Total time is checked against G-code.",
                            "Confirm actual printer, nozzle, plate and filament against the selected preset assumptions.",
                            "Slicing does not validate printed fit, adhesion, strength or long-term material creep."]}
        if library is not None:
            report["local_config"] = {"path": str(profile_path), "sha256": sha256(profile_path)}
        receipt = report
        if locations.portable:
            receipt, details = split_report(report, locations, temporary, output)
            sidecar = host_details(output / "verification.json", locations, details)
            (staged / delivered[2]).write_text(json.dumps(sidecar, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        (staged / "verification.json").write_text(json.dumps(receipt, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        # Discard verification toolpaths before making any delivery visible.
        shutil.rmtree(str(verification_dir))
        # mkdir is exclusive, including against a concurrently created destination.
        # Hard links publish only verified bytes and cannot replace existing files.
        output.mkdir()
        published = []
        try:
            for name in delivered:
                target = output / name
                os.link(str(staged / name), str(target))
                published.append(target)
        except OSError:
            for target in published:
                target.unlink()
            try:
                output.rmdir()
            except OSError:
                pass
            raise
    result = {"output_dir": str(output), "project": str(output / "project.3mf"),
              "verification": str(output / "verification.json"), "slicer_log": str(output / log_name),
              "total_estimated_seconds": slice_result["total_estimated_seconds"],
              "printer_contacted": False, "delivered_unsliced": True}
    if locations.portable:
        result["host_details"] = str(output / delivered[2])
    print(json.dumps(result))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, RuntimeError, ET.ParseError, zipfile.BadZipFile) as error:
        print("prepare_bambu: " + str(error), file=sys.stderr)
        sys.exit(1)
