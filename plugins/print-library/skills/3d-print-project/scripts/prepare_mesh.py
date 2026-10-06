#!/usr/bin/env python3
"""Validate an STL in millimetres and prepare a rigidly oriented print copy.

--axes lists the source coordinate for each output coordinate: Y,Z,X means
print X=source Y, print Y=source Z, print Z=source X. Signs are allowed, but
reflections are not. STL carries no units; optional CAD comparisons are the
only independent unit/nominal-geometry checks performed here.

Inside a record folder, library or other repository the receipt names files
by record-relative (or repository-relative) path and hash; absolute paths and
the interpreter go into the gitignored <report stem>.local.json sidecar.
"""

import argparse
import hashlib
import io
import json
import math
import os
from pathlib import Path
import sys
import tempfile
from contextlib import ExitStack

from host_details import Locations, host_details, sidecar_path

try:
    import numpy as np
    import trimesh
except ImportError as error:
    print("prepare_mesh: missing dependency; use the skill's Python environment: %s" % error, file=sys.stderr)
    sys.exit(1)


def rotation_for_axes(specification):
    tokens = [token.strip().upper() for token in specification.split(",")]
    if len(tokens) != 3:
        raise ValueError("--axes requires three signed axes, for example Y,Z,X")
    rotation = np.zeros((3, 3), dtype=np.float64)
    used = set()
    for row, token in enumerate(tokens):
        axis = token.lstrip("+-")
        if axis not in ("X", "Y", "Z") or token not in (axis, "+" + axis, "-" + axis):
            raise ValueError("invalid axis %r; use X, Y, Z with an optional sign" % token)
        if axis in used:
            raise ValueError("--axes must use each of X, Y, Z exactly once")
        used.add(axis)
        rotation[row, "XYZ".index(axis)] = -1 if token.startswith("-") else 1
    if round(float(np.linalg.det(rotation))) != 1:
        raise ValueError("--axes describes a reflection; a proper rotation (determinant +1) is required")
    return tokens, rotation


def load_stl(data, label):
    mesh = trimesh.load_mesh(file_obj=io.BytesIO(data), file_type="stl", process=False)
    if not isinstance(mesh, trimesh.Trimesh):
        raise ValueError("%s: STL did not contain a triangle mesh" % label)
    if len(mesh.vertices) == 0 or len(mesh.faces) == 0:
        raise ValueError("%s: mesh is empty" % label)
    if not np.isfinite(mesh.vertices).all():
        raise ValueError("%s: vertices must all be finite" % label)
    # STL repeats shared corners. Weld ONLY exactly equal coordinates, unlike
    # default merge_vertices rounding: no repair, rounding, or face removal.
    vertices, inverse = np.unique(np.asarray(mesh.vertices), axis=0, return_inverse=True)
    return trimesh.Trimesh(vertices=vertices, faces=inverse[mesh.faces], process=False)


def measurements(mesh, label):
    if len(mesh.faces) == 0 or len(mesh.vertices) == 0:
        raise ValueError("%s: mesh is empty" % label)
    if not np.isfinite(mesh.vertices).all():
        raise ValueError("%s: vertices must all be finite" % label)
    areas = mesh.area_faces
    if not np.isfinite(areas).all() or np.any(areas <= 0):
        raise ValueError("%s: mesh has nonfinite or zero-area triangles" % label)
    if not mesh.is_watertight:
        raise ValueError("%s: mesh is not watertight (no hole repair is performed)" % label)
    if not mesh.is_winding_consistent:
        raise ValueError("%s: mesh winding is inconsistent" % label)
    components = trimesh.graph.connected_components(
        mesh.face_adjacency, nodes=np.arange(len(mesh.faces)), engine="scipy"
    )
    if len(components) != 1:
        raise ValueError("%s: expected one connected solid, found %d" % (label, len(components)))
    bounds = mesh.bounds
    volume = float(mesh.volume)
    area = float(mesh.area)
    if not np.isfinite(bounds).all() or np.any(mesh.extents <= 0):
        raise ValueError("%s: mesh must have finite positive dimensions" % label)
    if not math.isfinite(volume) or volume <= 0:
        raise ValueError("%s: signed volume must be finite and positive (outward winding required)" % label)
    if not math.isfinite(area) or area <= 0:
        raise ValueError("%s: surface area must be finite and positive" % label)
    return {
        "bounds_mm": bounds.tolist(),
        "extents_mm": mesh.extents.tolist(),
        "volume_mm3": volume,
        "surface_area_mm2": area,
        "vertices": len(mesh.vertices),
        "triangles": len(mesh.faces),
        "watertight": True,
        "winding_consistent": True,
        "connected_components": len(components),
    }


def cad_comparisons(source, args):
    comparisons = {
        "cad_bounds": {"status": "not_checked", "reason": "--expected-bounds was not supplied"},
        "cad_volume": {"status": "not_checked", "reason": "--expected-volume-mm3 was not supplied"},
    }
    if args.expected_bounds is not None:
        expected = np.asarray(args.expected_bounds, dtype=np.float64).reshape(2, 3)
        if not np.isfinite(expected).all() or np.any(expected[1] <= expected[0]):
            raise ValueError("--expected-bounds must be finite with MAX greater than MIN on each axis")
        error = float(np.max(np.abs(np.asarray(source["bounds_mm"]) - expected)))
        if error > args.bounds_tolerance_mm:
            raise ValueError("CAD bounds mismatch: maximum error %.9g mm exceeds %.9g mm; check STL units" %
                             (error, args.bounds_tolerance_mm))
        comparisons["cad_bounds"] = {
            "status": "passed", "expected_bounds_mm": expected.tolist(),
            "maximum_absolute_error_mm": error, "tolerance_mm": args.bounds_tolerance_mm,
        }
    if args.expected_volume_mm3 is not None:
        expected_volume = args.expected_volume_mm3
        if not math.isfinite(expected_volume) or expected_volume <= 0:
            raise ValueError("--expected-volume-mm3 must be finite and positive")
        error_percent = abs(source["volume_mm3"] / expected_volume - 1.0) * 100.0
        if error_percent > args.volume_tolerance_percent:
            raise ValueError("CAD volume mismatch: error %.9g%% exceeds %.9g%%; check STL units" %
                             (error_percent, args.volume_tolerance_percent))
        comparisons["cad_volume"] = {
            "status": "passed", "expected_volume_mm3": expected_volume,
            "absolute_error_percent": error_percent, "tolerance_percent": args.volume_tolerance_percent,
        }
    return comparisons


def write_stable_stl(mesh, path):
    # 17 significant digits preserve double-precision corners, including thin
    # legacy triangles that binary STL's float32 coordinates can collapse.
    with path.open("x", encoding="ascii", newline="\n") as stream:
        stream.write("solid print_mesh\n")
        for face, normal in zip(mesh.faces, mesh.face_normals):
            stream.write("  facet normal %.17g %.17g %.17g\n    outer loop\n" % tuple(normal))
            for vertex in mesh.vertices[face]:
                stream.write("      vertex %.17g %.17g %.17g\n" % tuple(vertex))
            stream.write("    endloop\n  endfacet\n")
        stream.write("endsolid print_mesh\n")


def verify_preservation(source, prepared, saved, rotation, prepared_mesh, saved_mesh):
    # Numerical tolerances are independent of the user-selected CAD tolerance;
    # loosening a CAD comparison must never permit changed export dimensions.
    expected_extents = np.abs(rotation).dot(np.asarray(source["extents_mm"]))
    dimension_tolerance = max(1e-9, float(np.max(expected_extents)) * 1e-12)
    if not np.allclose(prepared["extents_mm"], expected_extents, rtol=0, atol=dimension_tolerance):
        raise ValueError("rotation changed nominal dimensions")
    for label, measured in (("rotation", prepared), ("STL round-trip", saved)):
        if not math.isclose(measured["volume_mm3"], source["volume_mm3"], rel_tol=1e-9, abs_tol=1e-9):
            raise ValueError("%s changed nominal volume" % label)
        if not math.isclose(measured["surface_area_mm2"], source["surface_area_mm2"], rel_tol=1e-9, abs_tol=1e-9):
            raise ValueError("%s changed surface area" % label)
    if not np.allclose(saved["bounds_mm"], prepared["bounds_mm"], rtol=0, atol=dimension_tolerance):
        raise ValueError("STL round-trip changed bounds")
    # Load-time exact welding sorts vertices. Compare the triangles themselves
    # so a topology change cannot pass just because its bounds and volume match.
    if not np.array_equal(prepared_mesh.triangles, saved_mesh.triangles):
        raise ValueError("STL round-trip changed triangle coordinates or winding")
    bounds = np.asarray(saved["bounds_mm"])
    if not np.allclose((bounds[0, 0] + bounds[1, 0], bounds[0, 1] + bounds[1, 1], bounds[0, 2]),
                       0, rtol=0, atol=dimension_tolerance):
        raise ValueError("saved mesh is not centered on XY and seated at Z=0")
    return {
        "status": "passed", "dimension_tolerance_mm": dimension_tolerance,
        "volume_and_area_relative_tolerance": 1e-9,
        "volume_absolute_tolerance_mm3": 1e-9, "area_absolute_tolerance_mm2": 1e-9,
        "triangle_coordinates_and_winding_exact": True,
        "centered_xy": True, "minimum_z_zero": True,
    }


def prepare(args):
    for name in ("bounds_tolerance_mm", "volume_tolerance_percent"):
        value = getattr(args, name)
        if not math.isfinite(value) or value < 0:
            raise ValueError("--%s must be finite and nonnegative" % name.replace("_", "-"))
    tokens, rotation = rotation_for_axes(args.axes)
    input_path = Path(args.input).expanduser().resolve(strict=True)
    requested_outputs = [Path(args.output).expanduser(), Path(args.report).expanduser()]
    if any(os.path.lexists(str(path)) for path in requested_outputs):
        raise ValueError("output and report must not already exist (including symlinks)")
    output_path, report_path = [path.resolve() for path in requested_outputs]
    if len({input_path, output_path, report_path}) != 3:
        raise ValueError("input, output, and report paths must be distinct, without aliases")
    if not input_path.is_file() or input_path.suffix.lower() != ".stl":
        raise ValueError("input must be an existing .stl file")
    for path in (output_path, report_path):
        if not path.parent.is_dir():
            raise ValueError("output parent directory does not exist: %s" % path.parent)
    locations = Locations(report_path.parent)
    sidecar = sidecar_path(report_path) if locations.portable else None
    if sidecar is not None and (os.path.lexists(str(sidecar)) or sidecar in (input_path, output_path)):
        raise ValueError("the host-details sidecar must not already exist: %s" % sidecar)

    source_bytes = input_path.read_bytes()
    source_mesh = load_stl(source_bytes, "source STL")
    source = measurements(source_mesh, "source STL")
    comparisons = cad_comparisons(source, args)
    rotated_vertices = np.asarray(source_mesh.vertices).dot(rotation.T)
    minimum = rotated_vertices.min(axis=0)
    maximum = rotated_vertices.max(axis=0)
    translation = np.array([-(minimum[0] + (maximum[0] - minimum[0]) / 2),
                            -(minimum[1] + (maximum[1] - minimum[1]) / 2), -minimum[2]])
    mesh = trimesh.Trimesh(vertices=rotated_vertices + translation, faces=source_mesh.faces, process=False)
    prepared = measurements(mesh, "prepared mesh")
    transform = np.eye(4)
    transform[:3, :3] = rotation
    transform[:3, 3] = translation

    # Stage beside each destination so hard-link publication is no-clobber and
    # stays on its destination filesystem. Roll back our links if either fails.
    with ExitStack() as stack:
        mesh_stage_dir = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix=".prepare-mesh-", dir=str(output_path.parent))))
        report_stage_dir = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix=".prepare-mesh-", dir=str(report_path.parent))))
        staged_mesh = mesh_stage_dir / "print.stl"
        staged_report = report_stage_dir / "report.json"
        write_stable_stl(mesh, staged_mesh)
        output_bytes = staged_mesh.read_bytes()
        saved_mesh = load_stl(output_bytes, "saved STL")
        saved = measurements(saved_mesh, "saved STL")
        comparisons["rigid_transform_and_stl_round_trip"] = verify_preservation(
            source, prepared, saved, rotation, mesh, saved_mesh
        )
        result = {
            "schema_version": 1, "status": "passed", "units": "mm",
            "units_note": "STL has no units. Coordinates are interpreted as mm; only supplied CAD comparisons independently check this assumption.",
            "source": {"path": str(input_path), "sha256": hashlib.sha256(source_bytes).hexdigest(), "mesh": source},
            "output": {"path": str(output_path), "sha256": hashlib.sha256(output_bytes).hexdigest(), "format": "ascii_stl_17_significant_digits", "mesh": saved},
            "report_path": str(report_path),
            "transform": {"axes": tokens, "axes_semantics": "source coordinate for output X,Y,Z, respectively",
                          "rotation_matrix": rotation.tolist(), "rotation_determinant": 1,
                          "translation_mm": translation.tolist(), "matrix_4x4": transform.tolist(),
                          "scaling": False, "reflection": False},
            "processing": {"welding": "exactly identical coordinates only", "geometry_repair": False},
            "comparisons": comparisons,
        }
        staged = [(staged_mesh, output_path), (staged_report, report_path)]
        if sidecar is not None:
            result["source"].update(locations.describe(input_path))
            result["output"].update(locations.describe(output_path))
            del result["report_path"]
            result["report"] = locations.describe(report_path)
            result["host_details"] = sidecar.name
            result["paths_note"] = locations.paths_note()
            staged_sidecar = report_stage_dir / "host.json"
            details = host_details(report_path, locations, {
                "source_path": str(input_path), "output_path": str(output_path), "report_path": str(report_path)})
            with staged_sidecar.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(json.dumps(details, indent=2, sort_keys=True, allow_nan=False) + "\n")
            staged.append((staged_sidecar, sidecar))
        report_text = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
        with staged_report.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(report_text)
        published = []
        try:
            for staged_file, destination in staged:
                os.link(str(staged_file), str(destination))
                published.append((staged_file, destination))
        except BaseException:
            for staged_file, destination in reversed(published):
                # Do not remove a file another process replaced after our link.
                if os.path.lexists(str(destination)) and os.path.samefile(str(staged_file), str(destination)):
                    destination.unlink()
            raise
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input", metavar="INPUT.stl")
    parser.add_argument("--output", required=True, metavar="PRINT.stl")
    parser.add_argument("--report", required=True, metavar="REPORT.json")
    parser.add_argument("--axes", required=True, help="source axes for output X,Y,Z; e.g. Y,Z,X or X,-Y,-Z")
    parser.add_argument("--expected-bounds", nargs=6, type=float, metavar=("MINX", "MINY", "MINZ", "MAXX", "MAXY", "MAXZ"))
    parser.add_argument("--bounds-tolerance-mm", type=float, default=0.02)
    parser.add_argument("--expected-volume-mm3", type=float)
    parser.add_argument("--volume-tolerance-percent", type=float, default=0.1)
    args = parser.parse_args()
    try:
        result = prepare(args)
    except Exception as error:
        print("prepare_mesh: %s" % error, file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
