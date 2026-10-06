"""Receipts inside a library carry relative paths; host details go to the sidecar (KTD17).

Run with the workshop interpreter (numpy and trimesh from requirements.txt):

    "$PYTHON" -m unittest discover -s "$SKILL_DIR/scripts/tests"
"""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

import prepare_bambu  # noqa: E402
from host_details import Locations  # noqa: E402

CORNERS = [(0, 0, 0), (20, 0, 0), (20, 10, 0), (0, 10, 0), (0, 0, 5), (20, 0, 5), (20, 10, 5), (0, 10, 5)]
TRIANGLES = [(0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7), (0, 1, 5), (0, 5, 4),
             (1, 2, 6), (1, 6, 5), (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7)]


def box_stl():
    lines = ["solid box"]
    for triangle in TRIANGLES:
        lines += ["  facet normal 0 0 0", "    outer loop"]
        lines += ["      vertex %d %d %d" % CORNERS[i] for i in triangle]
        lines += ["    endloop", "  endfacet"]
    return "\n".join(lines + ["endsolid box", ""])


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from strings(item)


def host_strings(value, host):
    """Strings that are absolute paths or mention a host folder."""
    return [s for s in strings(value) if s.startswith(("/", "~")) or any(h in s for h in host)]


class Scratch(unittest.TestCase):
    def setUp(self):
        self.scratch = Path(tempfile.mkdtemp(prefix="receipts-")).resolve()
        self.addCleanup(subprocess.run, ["rm", "-rf", str(self.scratch)], check=False)

    def library(self):
        root = self.scratch / "library"
        model = root / "models" / "bracket"
        model.mkdir(parents=True)
        (root / "library.json").write_text('{"schema_version": 1, "name": "Test"}\n')
        (root / "workshop.json").write_text(json.dumps({"schema_version": 1, "slicer": {"name": "Bambu Studio", "preset_ids": ["pla"]}}) + "\n")
        (model / "project.json").write_text('{"schema_version": 1, "id": "mdl-000000000000", "name": "Bracket"}\n')
        return root, model


class PrepareMeshTest(Scratch):
    def prepare(self, raw, revision):
        return subprocess.run([sys.executable, str(SCRIPTS / "prepare_mesh.py"), str(raw), "--output", str(revision / "part_print.stl"),
                               "--report", str(revision / "mesh_verification.json"), "--axes=X,Y,Z"],
                              capture_output=True, text=True, check=False)

    def test_receipt_in_a_library_has_no_absolute_paths_and_the_sidecar_has_them(self):
        root, model = self.library()
        revision = model / "design" / "r1"
        revision.mkdir(parents=True)
        raw = model / "design" / "bracket_raw.stl"
        raw.write_text(box_stl())
        outside = self.scratch / "downloads" / "other_raw.stl"
        outside.parent.mkdir()
        outside.write_text(box_stl())
        for source, expected in ((raw, {"path": "design/bracket_raw.stl"}), (outside, {"path": None, "name": "other_raw.stl"})):
            with self.subTest(source=source.name):
                run = self.prepare(source, revision)
                self.assertEqual(run.returncode, 0, run.stderr)
                receipt = json.loads((revision / "mesh_verification.json").read_text())
                self.assertEqual(host_strings(receipt, [str(self.scratch), str(Path.home())]), [])
                self.assertEqual({k: receipt["source"].get(k) for k in expected}, expected)
                self.assertEqual(receipt["output"]["path"], "design/r1/part_print.stl")
                self.assertEqual(receipt["report"], {"path": "design/r1/mesh_verification.json"})
                self.assertEqual(receipt["host_details"], "mesh_verification.local.json")
                self.assertRegex(receipt["source"]["sha256"], "^[0-9a-f]{64}$")
                sidecar = json.loads((revision / "mesh_verification.local.json").read_text())
                self.assertEqual(sidecar["details"]["source_path"], str(source))
                self.assertEqual(sidecar["details"]["output_path"], str(revision / "part_print.stl"))
                self.assertEqual(sidecar["interpreter"], sys.executable)
                self.assertEqual(sidecar["record_root"], str(model))
                self.assertEqual(sidecar["repository_root"], str(root))
                for name in ("part_print.stl", "mesh_verification.json", "mesh_verification.local.json"):
                    (revision / name).unlink()

    def test_an_existing_sidecar_is_never_overwritten(self):
        _, model = self.library()
        raw = model / "raw.stl"
        raw.write_text(box_stl())
        (model / "mesh_verification.local.json").write_text("{}")
        run = self.prepare(raw, model)
        self.assertNotEqual(run.returncode, 0)
        self.assertIn("sidecar must not already exist", run.stderr)
        self.assertFalse((model / "mesh_verification.json").exists())
        self.assertFalse((model / "part_print.stl").exists())

    def test_outside_any_repository_the_receipt_keeps_absolute_paths_and_has_no_sidecar(self):
        raw = self.scratch / "raw.stl"
        raw.write_text(box_stl())
        run = self.prepare(raw, self.scratch)
        self.assertEqual(run.returncode, 0, run.stderr)
        receipt = json.loads((self.scratch / "mesh_verification.json").read_text())
        self.assertEqual(receipt["source"]["path"], str(raw))
        self.assertEqual(receipt["report_path"], str(self.scratch / "mesh_verification.json"))
        self.assertFalse((self.scratch / "mesh_verification.local.json").exists())


class PrepareBambuTest(Scratch):
    def local_config(self):
        local = self.scratch / "config" / "local.json"
        presets = local.parent / "presets"
        presets.mkdir(parents=True)
        for name in ("machine", "process", "filament"):
            (presets / (name + ".json")).write_text("{}")
        slicer = self.scratch / "Slicer"
        slicer.write_text("#!/bin/sh\n")
        slicer.chmod(0o755)
        local.write_text(json.dumps({
            "schema_version": 1,
            "software": {"bambu_studio": {"path": str(slicer)}},
            "presets": {name: {"machine": "presets/machine.json", "process": "presets/process.json", "filament": "presets/filament.json",
                               "build_volume_mm": [180, 180, 180], "require_supports": False, "assumptions": [],
                               "expected_settings": {"layer_height": "0.2"}} for name in ("pla", "petg")}}))
        return local, slicer

    def test_a_library_workshop_merges_with_local_configuration(self):
        root, _ = self.library()
        local, slicer = self.local_config()
        profile_path, profile, library = prepare_bambu.load_workshop(root / "workshop.json", local)
        self.assertEqual((profile_path, library["slicer"]["preset_ids"]), (local, ["pla"]))
        _, profiles, executable = prepare_bambu.load_preset(profile_path, profile, "pla", None, library)
        self.assertEqual(executable, slicer.resolve())
        self.assertEqual(profiles["machine"], (local.parent / "presets" / "machine.json").resolve())
        with self.assertRaisesRegex(ValueError, "not listed in the library workshop.json"):
            prepare_bambu.load_preset(profile_path, profile, "petg", None, library)

    def test_a_library_workshop_with_host_paths_is_refused(self):
        root, _ = self.library()
        local, _ = self.local_config()
        (root / "workshop.json").write_text(json.dumps({"schema_version": 1, "software": {"bambu_studio": {"path": "/Applications/x"}}}))
        with self.assertRaisesRegex(ValueError, "host paths and preset files belong in local configuration"):
            prepare_bambu.load_workshop(root / "workshop.json", local)

    def test_a_standalone_profile_is_still_the_whole_workshop(self):
        local, slicer = self.local_config()
        profile_path, profile, library = prepare_bambu.load_workshop(local, None)
        self.assertIsNone(library)
        self.assertEqual(prepare_bambu.load_preset(profile_path, profile, "petg", None, None)[2], slicer.resolve())

    def test_the_committed_receipt_has_relative_paths_and_hashes_and_the_sidecar_has_the_host_details(self):
        root, model = self.library()
        local, slicer = self.local_config()
        mesh = model / "design" / "r1" / "part_print.stl"
        mesh.parent.mkdir(parents=True)
        mesh.write_text(box_stl())
        output = model / "design" / "r1" / "bambu"
        temporary = model / "design" / "r1" / ".bambu-prepare-x"
        digest = "0" * 64
        report = {
            "schema_version": 1, "preset_id": "pla",
            "workshop": {"path": str(root / "workshop.json"), "sha256": digest},
            "local_config": {"path": str(local), "sha256": digest},
            "profiles": {"machine": {"path": str(local.parent / "presets/machine.json"), "sha256": digest}},
            "sources": [{"path": str(mesh), "sha256": digest, "bytes": 10}],
            "slicer": {"path": str(slicer), "sha256": digest},
            "commands": [{"argv": [str(slicer), "--export-3mf", str(temporary / "delivery/project.3mf")], "cwd": str(temporary),
                          "returncode": 0, "timeout_seconds": 300},
                         {"argv": [str(slicer), "--slice", "1"], "cwd": str(temporary), "returncode": 0, "timeout_seconds": 300}],
            "slicer_log_warnings": ["warning: " + str(temporary / "inputs/part_print.stl") + " has a thin wall", "warning: " + str(slicer) + " plugin"],
            "project_sha256": digest,
            "notes": ["All slicer output is retained in slicer.log; warnings are not suppressed."],
        }
        receipt, details = prepare_bambu.split_report(report, Locations(output.parent), temporary, output)
        self.assertEqual(host_strings(receipt, [str(self.scratch), str(Path.home())]), [])
        self.assertEqual(receipt["sources"], [{"path": "design/r1/part_print.stl", "sha256": digest, "bytes": 10}])
        self.assertEqual(receipt["workshop"], {"path": None, "repository_path": "workshop.json", "sha256": digest})
        self.assertEqual(receipt["slicer"], {"path": None, "name": "Slicer", "sha256": digest})
        self.assertEqual([c["step"] for c in receipt["commands"]], ["export", "slice"])
        self.assertEqual(receipt["slicer_log_warnings"], ["warning: <temp>/inputs/part_print.stl has a thin wall", "warning: <slicer> plugin"])
        self.assertEqual((receipt["host_details"], receipt["slicer_log"]), ("verification.local.json", "slicer.local.log"))
        self.assertEqual(receipt["project_sha256"], digest)
        self.assertEqual(details["slicer_path"], str(slicer))
        self.assertEqual(details["sources"], [str(mesh)])
        self.assertEqual(details["local_config_path"], str(local))
        self.assertEqual(details["commands"], report["commands"])


if __name__ == "__main__":
    unittest.main()
