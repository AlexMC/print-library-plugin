# Bambu project preparation

## Runtime

Read `software.python.path` and `software.bambu_studio.path` from local configuration: `~/.config/3d-print/local.json`, or the legacy combined profile `~/.config/3d-print/workshop.json` on older setups (see `templates/local.example.json`). These are host paths; they never go into a library's `workshop.json`. The Bambu helper itself is stdlib-only; mesh preparation needs this skill's pinned requirements. If reinstalling, create a durable virtual environment with Python 3.8–3.11 and install `requirements.txt`; use the workshop runtime, not a temporary project interpreter. Confirm compatibility before changing Python/dependency versions.

All helpers have `--help`. Existing output files/directories are deliberately refused. Create a fresh revision directory first; each output's parent must exist. Do not bypass refusal by deleting the user's previous artifacts.

On Apple Silicon, a Rosetta-launched Python process can select an x86_64 interpreter against ARM-only NumPy wheels. Check architecture before reinstalling dependencies. With a confirmed ARM environment, this is a useful smoke check:

```sh
/usr/bin/arch -arm64 "$PYTHON" "$SKILL_DIR/scripts/prepare_mesh.py" --help
```

This is an environment-specific invocation, not a portable helper guarantee. Record the working executable/invocation; `--slicer` accepts one executable path, not a shell command with an architecture prefix.

## Choose a preset deliberately

The local configuration's `presets` map contains named machine/process/filament snapshots. `prepare_bambu.py` requires `--preset`; it has no automatic material/process default. Preset paths resolve relative to the local configuration file. In a library, pass the library's `workshop.json` as `--workshop`: the helper merges it with local configuration (`--local-config`, default `~/.config/3d-print/local.json`, else the legacy profile), refuses a library `workshop.json` that holds `presets` or `software`, and, when the library lists `slicer.preset_ids`, accepts only a listed preset. Outside a library `--workshop` is the combined profile, as before. Keep its `expected_settings`, `build_volume_mm`, `require_supports` and `assumptions` consistent with the selected files.

The included `controller-supports-pla` preset reproduces the successfully sliced controller project: A1 mini, assumed 0.4 mm nozzle/Textured PEI, Generic PLA, 0.2 mm layers, six walls, 35% gyroid, six top/bottom layers, build-plate tree supports and 5 mm brim. This is evidence for that project, not a calibrated universal recipe. A future support-free part should explicitly select an appropriate preset with `require_supports: false`.

Changing the printer/nozzle/plate fields in the profile does not regenerate preset files. Update/select matching presets and their expectations too; never silently claim an old slice applies to new hardware.

Use an authentic matching native machine profile, including its command templates, and compatible filament/process profiles. Renaming another printer's profile is not a hardware conversion. Compare speed settings with the installed profile for the actual nozzle/extruder variant, but retain the actual filament's flow and temperature limits unless separately justified. A higher requested speed is not a proportional time-saving guarantee.

### Preserve the inputs behind each receipt

The helper stages temporary copies and records hashes; it does not retain those copies or freeze their originals. The caller must keep named, immutable machine/process/filament and workshop snapshots for every accepted measurement. Finish the snapshot before measuring. Do not append presets to a workshop file already cited by a receipt; use a separate snapshot. If artifacts are relocated, retain the exact bytes and record both their provenance and resolvable current locations.

Include changed safety/cost-critical fields in `expected_settings`. The helper checks the listed fields, not every possible profile setting or actual installed hardware.

## Compare cost before committing to the print

1. Start with a representative full-size part for each materially different geometry/support problem. Record the baseline and intended physical outcome; a coupon alone does not expose full-height support or cooling costs.
2. Separate model, supports/interfaces and brim/startup overhead where reliable diagnostics are available. Thin members may contain very little sparse infill, so lowering infill percentage can save almost nothing.
3. Measure a small, hypothesis-led set of changes. Isolate orientation/support strategy, motion settings, layer height and infill before combining winners. Preserve geometry and clearances unless a CAD change is agreed. Do not make a large sweep mandatory.
4. Keep each variant in a fresh directory with its settings, source identities, warnings and result. Persist results as they complete, including failures. Distinguish an environment failure from a measured losing candidate.
5. Re-slice the selected combination and final plate arrangement. Cooling, support layout, travel and repeated startup costs mean standalone-part estimates need not add up to the final plates.
6. Compare identical scopes. Report structural-part savings separately from new fit checks, and also give the complete recommended validation sequence. A time improvement does not imply a similar material improvement.
7. Revalidate affected mating conditions when orientation/process changes. Reuse compatible existing keys or shared pegs where that still tests the real interfaces. If material remains high, discuss a print-oriented CAD/assembly change rather than silently weakening members or removing necessary support.

Extrusion-role accounting is a separate diagnostic, not a built-in helper feature. When using it, handle absolute/relative extrusion, resets, retractions, depositing moves including arcs, filament diameter/density and custom/purge exclusions; reconcile the result with the slicer's aggregate estimate and report discrepancies. It is still a slicer/toolpath estimate, not measured spool consumption.

## Check support reachability, not just support quantity

- `support_used` is a plate-level flag, not evidence of support at every required contact or on every object. A warning-free slice is not a support-coverage certificate.
- Normal supports restricted to the build plate may not reach regions above existing model surfaces. Near-zero support can reflect that restriction, not improved printability. Compare reachable alternatives, inspect the layer paths/contact regions and justify any reliance on bridging before accepting the saving.
- Normal/build-plate-only is not universally wrong, and trees are not universally better. Choose by the actual geometry. Supports starting on the model can restore access but change surface quality and removal risks.
- Bambu's threshold angle is measured from the horizontal; increasing it requests support for more slopes, not fewer. Do not transfer angle conventions from another slicer.
- Inspect undersides, long spans, floating starts, support roots/interfaces, bed contact and removal access in actual sliced evidence. A bridge extrusion move may include supported anchors; its length alone is not the unsupported span.
- Do not disable supports or change `require_supports` merely to obtain a cheap passing result. For a coupon that may legitimately need no support, `require_supports: false` only relaxes the metadata requirement; support generation remains controlled by the process settings.

Manufacturer references: [Bambu support settings](https://wiki.bambulab.com/en/software/bambu-studio/support), [Prusa infill guidance](https://blog.prusa3d.com/everything-you-need-to-know-about-infills_43579/), [layer height and perimeters](https://help.prusa3d.com/article/layers-and-perimeters_1748). Apply their guidance to measured candidates, not universal presets.

## What the helper proves

- Requested settings survived into the delivered 3MF.
- Exported 3MF transforms are checked for proper rotation without scaling, reflection or out-of-plane tipping. Arrangement may rotate around Z.
- Objects sit on the bed and fit the configured rectangular XYZ build volume. This is not an independent collision/exclusion-zone check or an exported-mesh equivalence comparison against the source STL.
- The saved project is unsliced; a separate actual temporary slice produced one plate with every requested object printed.
- Parsed numeric G-code arguments are finite, at least one motion command contains a positive E argument, and total estimated duration matches the G-code header. This is not net-deposition accounting or measured elapsed print time.
- When `require_supports` is true, the slicer's plate-level `support_used` flag must be true. The helper does not independently validate coverage, contact quality or removability.

The helper uses isolated slicer settings and never sends anything to a printer. Temporary G-code is discarded. Inside a record folder, library or other repository the delivery is `project.3mf`, `verification.json` (relative paths and hashes only) and the gitignored `verification.local.json` (absolute paths, commands, slicer location) and `slicer.local.log` (raw slicer output); elsewhere it is `project.3mf`, `verification.json` and `slicer.log` with absolute paths.

The earlier mesh receipt records any supplied native-CAD comparisons and STL round-trip evidence; absent CAD comparisons are explicitly not checked. The Bambu helper does not compute per-role material consumption, compare candidate costs or inspect images. Warnings are collected but are not automatically failing conditions; examine them separately from the pass flag.

If automatic arrangement creates multiple plates, retain the single-plate verification contract. Prepare separately verified projects or establish a genuinely fitting arrangement and remeasure it; do not weaken checks or silently omit requested parts. State any project split and total all final plates.

Use stable authored plate IDs in `outcomes`, independent of container paths. Read `verification.json` before recording per-run contents: explicitly map each `sources` entry to a component revision, using zero-based `receipt_sources` indices when hashes alone are ambiguous. Derive instance counts from that mapping; required BOM quantities and repeat counts are separate authored facts.

For repeated instances, make immutable uniquely named copies of the prepared STL before invoking the helper. Duplicate paths, aliases and case-insensitive stems are rejected; extra copies are not extra logical parts. Two authored plate records may refer to different plates in one existing 3MF, but this helper still verifies only one plate per invocation. A manually combined container has different bytes: retain its exact project path, but do not attach either single-plate receipt as verification of that container or rewrite its receipt hash. Leave verification unrecorded until the combined container is actually checked. See `references/project-record.md` for the portable source contract and the limits of receipt matching.

## Review before delivery

Read warnings and report them without broadly suppressing categories. In the observed Bambu version, traditional-timelapse warnings occurred and first-layer timing metadata was nonsensical. Leave traditional timelapse off for the controller preset; total timing is checked against the actual G-code header instead. Do not conceal new warnings under that precedent.

Inspect the 3MF's actual `Metadata/plate_1.png` rendering for geometry/arrangement, or open the project in Bambu Studio if practical. Even a thumbnail extracted from a sliced archive may be identical to the unsliced model thumbnail and show no supports. Use a real sliced layer view or a separately identified toolpath visualization for support inspection; label sampling/projection limits. The helper discards its temporary G-code, so later diagnostics require a new local slice with its own provenance, not a claim that the original toolpaths were retained.

Report total time/material estimates with their scope and warnings. Confirm only hardware/material facts that are still unknown; do not repeatedly ask about an already confirmed nozzle or plate. Tell the user to open the delivered `.3mf` **as a project**, retaining its embedded settings, rather than importing only geometry. Keep process-specific plate files and the planned fit/assembly sequence explicit.

Geometry checks and a successful slice do not certify bed adhesion, printed fit, strength, fatigue or PLA creep. Ask for physical feedback tied to the revision.
