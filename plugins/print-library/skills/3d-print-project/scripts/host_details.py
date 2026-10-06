"""Portable receipt paths and the gitignored host-details sidecar (KTD17).

A receipt saved inside a record folder (a folder holding project.json), a
library (library.json at its root) or another Git checkout is committed, so it
names files by record-relative path, or repository-relative path for files
elsewhere in the repository, plus their hashes. Absolute paths, commands,
working folders, the interpreter and the slicer location go into a sidecar
next to the receipt, ``<receipt stem>.local.json``, which the library and
project ``.gitignore`` files exclude. A receipt saved outside any repository
keeps the earlier absolute paths and gets no sidecar.
"""

import os
import platform
from pathlib import Path
import sys

SIDECAR_SUFFIX = ".local.json"
LOG_SUFFIX = ".local.log"


def _inside(path, root):
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return None


def sidecar_path(receipt):
    """``verification.json`` -> ``verification.local.json``."""
    stem = receipt.name[:-len(".json")] if receipt.name.endswith(".json") else receipt.name
    return receipt.with_name(stem + SIDECAR_SUFFIX)


class Locations:
    """Where a receipt lives: its record folder and repository root, when any."""

    def __init__(self, receipt_dir):
        self.record = None
        self.repository = None
        current = Path(receipt_dir).resolve()
        for folder in [current] + list(current.parents):
            if self.record is None and (folder / "project.json").is_file():
                self.record = folder
            if (folder / "library.json").is_file() or (folder / ".git").exists():
                self.repository = folder
                break

    @property
    def portable(self):
        return self.record is not None or self.repository is not None

    def describe(self, path):
        """Path fields for a receipt: record-relative, else repository-relative, else only the file name."""
        path = Path(path).resolve()
        if self.record is not None:
            relative = _inside(path, self.record)
            if relative is not None:
                return {"path": relative}
        if self.repository is not None:
            relative = _inside(path, self.repository)
            if relative is not None:
                return {"path": None, "repository_path": relative}
        return {"path": None, "name": path.name}

    def paths_note(self):
        base = "record folder" if self.record is not None else "repository root"
        return ("Paths are relative to the " + base + "; repository_path entries are relative to the repository root. "
                "Absolute paths, commands and the interpreter are in the gitignored " + SIDECAR_SUFFIX + " sidecar.")


def scrub(text, replacements):
    """Replace host strings (longest first) with placeholders in free text copied into a receipt."""
    for value, placeholder in sorted(replacements.items(), key=lambda item: -len(item[0])):
        if value:
            text = text.replace(value, placeholder)
    return text


def host_details(receipt, locations, details):
    """The sidecar document for ``receipt``."""
    return {
        "schema_version": 1,
        "receipt": receipt.name,
        "note": "Host-specific details for " + receipt.name + ". Machine-local: never commit this file.",
        "record_root": str(locations.record) if locations.record is not None else None,
        "repository_root": str(locations.repository) if locations.repository is not None else None,
        "cwd": os.getcwd(),
        "argv": list(sys.argv),
        "interpreter": sys.executable,
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "details": details,
    }
