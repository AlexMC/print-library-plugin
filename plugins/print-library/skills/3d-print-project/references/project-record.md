# Model record conventions

A model record is one `project.json`. In a library the tool's `draft` (or `add-version --remix-as`) writes a new model's record; in a standalone project copy `templates/project.json` (the minimal core layer). Fill only supported facts; empty or null fields mean unknown, never permission to invent. Keep the record small and human-readable. The JSON Schemas in 3dhub's `schemas` folder describe the shapes; the checker reports problems with fixed wording.

## Where records live

- **Library:** a repository with a root `library.json` and one folder per model. The model set is every `models/<slug>/project.json`; `library.json` never lists models, so two pull requests adding models never edit the same file. A folder without `project.json` is not a model.
- **Standalone project:** a repository with a root `project.json`. It keeps working exactly as before; the record root is the repository root.
- `library.json` holds library settings (`name`, `viewer_origin`) and `links`: projects kept in their own repositories, each `{ "repo": "owner/name", "name": "Display name" }`. Linking never moves a model; moving a model out of a library is not supported yet.
- `workshop.json` (library root) holds shareable workshop facts: printer, nozzle, build plate, materials and slicer preset ids. Host paths — slicer executables, Python interpreters, profile folders — stay in local configuration and never enter the repository.

```text
library.json                 settings, linked projects, viewer origin
workshop.json                printer, nozzle, materials, slicer (no host paths)
models/<slug>/
  project.json               core layer (+ printing/design when used)
  original/                  downloaded bytes, never edited
  versions/<version>/        remixes and updates
  prints/<date>-<key>.json   one result per print
  prints/<key>/              photos for that print
  thumbnail.png              extracted from 3MF or supplied
```

## Who writes what in a library

- **Core layer, prints, details, workshop:** only the library tool (`draft`, `add-version`, `log-print`, `details`, `workshop set`), so the agent, the inbox Action and the issue forms produce identical bytes. `draft --origin original` records the person's own design (`origin.kind` `original`, v1 of kind `own`).
- **Design layer:** written by hand in the model's `project.json`, with its sources, exports and receipts inside the model folder.
- **Every change** reaches the default branch as a pull request from `library/agent/<key>` (agent), `library/draft/*` or `library/print/*` (Actions), after the `Library check`.

## Paths

- Every path in a record is relative to the folder holding its `project.json` (`models/<slug>/` in a library) and may not leave it. Never use absolute, `~` or other host paths, URLs, `.`/`..` segments or empty segments. Readers reject such references without reading anything.
- Readers report files with their repository path (`models/<slug>/original/benchy.3mf`); records store the folder-relative path (`original/benchy.3mf`).
- Slugs never change after merge. References between models use the immutable `id`.
- `workshop_profile` in older records names a living host file. Readers keep it as legacy information and never resolve it; do not add it to new records.
- Helper receipts (`mesh_verification.json`, `bambu/verification.json`) saved in a repository use the same rule: record-relative `path` (or `repository_path` for a file elsewhere in the repository, or only `name` for a file outside it) plus `sha256`. Absolute paths, commands, working folders, the interpreter and the slicer location are in the `*.local.json` sidecar beside the receipt, which `.gitignore` excludes; never commit or cite a sidecar.

## Core layer (required)

Every model record carries the core layer. `schema_version` stays `1`; new fields are additive and unknown fields are preserved.

| Field | Meaning |
|---|---|
| `id` | Immutable model id written once when the model is drafted; independent of the folder slug |
| `core_level` | Integer; absent means 1. A record with a higher level needs a newer checker |
| `name` | Display name |
| `origin` | `kind` (`downloaded`, `remix` or `original`), `source_url`, `site`, `designer`, `retrieved` (date) |
| `license` | `state` (`known`, `unknown`, `restricted`), `name`, `flags` (`attribution`, `noncommercial`, `no_derivatives`, `share_alike`) |
| `versions` | `[{ id, kind, files, based_on, note, date }]`; `kind` is `upstream`, `remix` or `own`; each file has `path`, `sha256`, `units` for a mesh that records none (`mm`, `cm`, `m` or `in`; the tool writes `mm` for STL and OBJ, and a 3MF keeps its declared unit) and, for downloads, `original_filename` |
| `remix_of` | `{ id, slug, version, commit, attribution }` for a remix: the original's id, slug and version, the full commit it was taken from, and a copy of its attribution (`name`, `designer`, `source_url`, `license`) |
| `sources` | Per-file overrides `[{ path, source_url, site, designer, license }]` when one file came from somewhere other than the model's origin |

- **Downloaded originals are never edited.** Bytes under `original/` stay identical to the recorded `sha256`; a change becomes a new version under `versions/<version>/`.
- **License state is never guessed.** Only these names map to a state: CC0, CC BY, BY-SA, BY-NC and BY-NC-SA (known, with their attribution, noncommercial and share-alike flags); BY-ND and BY-NC-ND (restricted, no derivatives); the GPL family (known, share-alike); "Standard Digital File License" and "MakerWorld Exclusive License" (restricted). Any other name is `unknown` until a person decides. A recorded restriction is never relaxed.
- **Lineage stays in one library.** `remix_of` resolves by `id` and keeps working when the original is renamed or deleted, because the attribution is copied. License restrictions pass down the chain. Projects linked from `library.json` are not followed for comparison.

## Printing layer (optional)

- One file per print: `prints/<date>-<key>.json` with `version`, `commit` (the full commit the print was logged at), `date`, `outcome` (`success`, `partial`, `failed`), `printer`, `nozzle_mm`, `material`, `note` and `photos` (folder-relative paths under `prints/<key>/`).
- Add `photos` only for actual photographs supplied by the user; never generated or rendered images.
- An existing `print_feedback` array stays readable; each row is shown as a legacy print result bound to its `version` (or its recorded revision label). New results go to `prints/`.

## Design layer (optional)

The fields below, and the provenance, handoff, capture, outcome and work sections that follow, record an agent-assisted design. They are checked only when present.

- `revision`: a meaningful local revision label; do not imply that it is an Onshape version ID.
- `stage`: current factual stage, such as brief, design_agreed, cad_verified, digital_verification_complete, or awaiting_print_feedback. Do not mark a physical result complete merely because CAD or slicing passed.
- `next_action`: one concrete continuation or the exact missing prerequisite. New sessions begin here, after checking relevant evidence.
- Keep accepted workshop/profile snapshots immutable and referenced by the receipts that consumed them. Use fresh paths for variants and preserve original receipt paths/hashes when relocating exact copies. Large experiment logs belong outside the main record.
- Link durable process learnings from the project record so a new session can discover them without replaying the investigation. Keep general rules in the skill, project measurements in evidence, and physical observations in prints.
- The optional `outcomes` and `work` extensions below remain part of source schema version 1. Empty extensions mean no outcome/roadmap has been recorded; they do not designate a printable version.

## Source control and process provenance

- Keep reusable instructions/scripts in the process repository and each design's source, exports, final printer projects, verification and physical feedback in its own repository or library. The canonical process is the `print-library` plugin in https://github.com/AlexMC/3dhub (`plugins/print-library/`); the installed skill reports its source path and tool version at start. Do not independently edit a second installed copy.
- `process`: repository URL, full commit ID or plugin version, the tool version, dirty state and scope for the current work. Resolve the installed skill's real path before obtaining its Git commit. A dirty checkout needs a retained source snapshot/hash; never claim that a clean commit alone describes it.
- For every newly prepared revision, retain the actual process identity in that revision's handoff or a linked sidecar. A top-level current pointer does not replace per-revision provenance. Record explicit upgrades and preserve previous identities.
- Existing work imported before Git has no historical process commit. Keep it null in `source_control.historical_process_commit`; record the process snapshot at import separately and do not backdate its use. `source_control.import_manifest` links the original file hashes and any external-path-to-snapshot mapping.
- Preserve historical receipts and consumed profile bytes. Keep missing temporary paths as historical facts; resolve retained evidence through the import manifest rather than rewriting receipts to appear freshly verified. Host-specific slicer and profile configuration remains local; archived copies do not prove current runtime availability or reproduce an earlier mutable file version.
- Keep Onshape as the authoritative cloud source when already designated. Retain document/workspace/element/version identifiers and local source/exports in Git, without claiming Git captures the complete native Onshape history. Unknown revision IDs and source licenses stay unknown.
- Exclude credentials, agent sessions, caches and disposable slices. Keep evidence logs and delivered STL/3MF files; ignore a duplicate package only after proving its members are retained. Review source licenses before public distribution.

## Scope and stage handoffs

- In `brief.requirements`, capture requested deliverables and their observable acceptance criteria alongside the functional requirements. In `decisions`, record whether live Onshape and printer-specific preparation are included, skipped with a reason, or blocked by a named prerequisite. This uses the existing template; no separate task database or additional schema is required.
- Intake is ready when critical dimensions/interfaces, load/environment constraints and consequential manufacturing assumptions have sources and an agreed basis. Unknowns do not acquire defaults merely because modelling has started.
- A local editable CAD file or an existing mesh can be the source of truth; cloud identifiers remain null when Onshape is not used. If Onshape is authoritative, identify the exact model/revision behind each raw export. Do not report a local mesh as a cloud export without that provenance.
- Treat `stage` as a factual milestone, not an automatic pipeline. Optional branches and per-part progress live in the scoped decisions/evidence. Resume at the first unmet dependency, preserve settled decisions, and leave one concrete `next_action`.
- At handoff, account for every requested output and quantity: current source, raw/prepared STLs, optional CAD link and optional printer projects. Record digital checks with their actual scope and physical checks separately. A complete STL-only delivery needs no printer project; a requested but unavailable printer project is blocked, not silently skipped.
- Link assembly/hardware instructions, print/test sequence and any larger manifest from the record. Digital delivery can be complete while physical acceptance remains pending; do not keep manufacturing new artifacts merely to fill an optional stage.
- Maintain `outcomes` and `work` at the actual design, export, preparation, delivery and feedback gates below. Reuse receipt facts; ask the user only for missing intent or consequential choices, not values already present in evidence.

## What to capture

- `brief`: purpose, references, requested outputs, observable acceptance criteria, load/environment assumptions, appearance, material and hardware policy. For strength requirements, retain mass/force, direction, span/lever arm, mounting, duration/cycles and consequences of failure where relevant, not just “strong.”
- `measurements`: objects with name, value, units, status, basis/source, and `includes_clearance` where relevant. Unknowns remain null or explicitly unconfirmed. A per-side clearance is not a total gap.
- `decisions`: decision, reason, and conditions. Preserve why an orientation, joint or dimension was chosen, not the entire conversation.
- `cad`: current source of truth and exact cloud identifiers. A local snapshot is a backup. If only some parts were recreated in Onshape, say which; do not relabel legacy parts as migrated. Record actual version/microversion when available; otherwise leave it null.
- `renders`: optional list of existing images that depict the design, for readers to show as project visuals: `path`, `view` (for example `"Side"`), `design_revision` (the CAD/design revision depicted; omit when it is not one recorded revision) and a short `caption`, plus an optional `evidence` or `source` path. Record only images that actually exist, such as reviewed CAD views or generator previews; keep older revisions' renders with their own `design_revision` rather than relabelling them. Say in the caption when a render predates current parts. A render is not a photograph of a print and never physical evidence.
- `parts`: name, `revision`, source snapshot, `raw_export`, `prepared_print_mesh`, `units`, explicit orientation, important CAD dimensions and relevant parameters. A part referenced by an outcome must also have a stable `id`; the `(id, revision)` pair must be unique. Preserve the ID through renames and revisions rather than deriving it from a filename or array position. Legacy parts without outcome references need not acquire IDs. Store native bounds/volume when available so mesh checks can detect wrong units, axes or exports.
- `printing`: explicit preset/project references, hardware-assumption status and physical-validation state. Multiple process-specific plates need explicit preset/project lists or a referenced manifest; distinguish structural plates from fit checks and retain their individual scopes.
- `verification`: kind, passed/failed/not_checked status, evidence path and scope. Geometry-specific motion/interference checks stay with their project. Large metrics and logs belong in referenced evidence files rather than copied into this record.
- `print_feedback` (legacy; new results are `prints/` entries): actual user observations. Include revision, material/spool, nozzle, plate, layer height, orientation/preset, fit/failure measurements and resulting decision. List the exact `project_files` the observation covers when the user identifies them. Add folder-relative `photos` only for actual photographs supplied by the user; never generated or rendered images. No feedback means an empty array, not an inferred success.
- When comparing printer-specific candidates, record baseline and selected time/material for the same part quantities, then separately report new validation costs and the full recommended sequence. Do not extrapolate a subset trial to a full assembly or batch without measuring the actual layout. No slicing-cost record is required for STL-only scope.
- Treat progress as a separate observation: “prints underway” does not identify which plate/revision unless the user says so, and does not establish completion, fit, support removal or strength. Record unknown identities/results explicitly; preserve prior successful tests with their original conditions.
- New orientations of an existing coupon can share the same source geometry. List each pose/process and which actual mating pair it checks; do not label all variants physically validated because the original coupon passed.

Keep physical tolerance findings with their conditions and evidence in the model's records. A library's `workshop.json` holds only printer, nozzle, build plate, material and slicer facts (written with `workshop set`); it has no tolerance field. Never copy project-specific requirements or one successful clearance into universal defaults. Keep secrets and signed download links out of all records.

## Versioned outcomes

Use this optional extension when handing a project to an outcome-aware reader. It describes intended builds, not printer queues or manufacturing certification. Existing records without it remain valid.

### Catalogue and immutable references

`outcomes.definitions` contains definitions local to this record's Git snapshot. A definition has a stable `id`, unique within that array, a human-readable `name`, optional `requested_outputs` (for example `["stl"]` or `["stl", "printer-project"]`), and `variants`.

`outcomes.working` is one reference or null. `outcomes.printable` is an array of explicitly designated printable references. Each reference has:

| Field | Meaning |
|---|---|
| `id` | Unique catalogue reference ID across both `working` and `printable` |
| `name` | Human-readable selection label |
| `outcome_id` | Definition ID at the referenced snapshot |
| `variant_id` | Variant ID; a local working reference may leave it null to request selection |
| `commit` | Full 40-character same-repository Git SHA, or null/absent for a local definition |

Printable references require both an immutable commit and a variant ID. Any pinned working reference also requires a variant ID; only local working definitions can leave the variant for selection. Resolve the definition in the same record folder at that commit. The target must contain that local definition; do not chain references through another catalogue, use a moving branch/tag, or reference another repository.

`outcomes.default_selection` is null or an object with `reference_id` and `variant_id`. A pinned reference's variant cannot be overridden. With multiple outcomes/variants, either record an intentional default or leave selection to the reader; do not infer a default from recency or array order.

First commit the complete definition and retained artifacts. Then designate that already-committed snapshot as printable in a subsequent record. Before starting a replacement version, preserve the previous printable reference. Never attempt to embed a commit's own future SHA in itself.

The root `revision` remains a label for the project record and its legacy history. It is not an outcome reference. Outcome IDs identify project versions; variant IDs identify continuing alternatives across those versions. Keep model and plate IDs stable through renames/reordering. Do not regenerate IDs from array positions or filenames.

### Variant composition and visuals

Each variant has an `id` unique within its definition, `name`, `members`, optional `assembly`, and `plates`. A member contains `part_id`, `revision`, `quantity`, an optional explicit `mesh` path, and an optional expected `sha256` for that mesh. `part_id` must equal the logical component's `parts[].id`; `revision` must identify the intended revision, not whichever revision happens to be newest. Each logical `part_id` appears once in the variant's `members` list, with its total required quantity.

When `mesh` is absent, a reader may use the part with that exact `id` and `revision`: its `prepared_print_mesh`, then its `raw_export`. It must not substitute a different revision. An explicit mesh can retain an older input for inspection while exposing its mismatch with the working composition; it does not replace logical part identity. Required quantities are positive safe integers; null/missing quantities are unknown.

An assembly representation contains `mesh`, `image`, `units`, and `members`. Its `members` list records the component IDs, revisions, quantities and available mesh hashes that the visual depicts. A whole assembled STL is already in assembly coordinates. Use the mesh receipt's units (`"mm"` for the bundled mesh helper), not a slicer setting's unit label; leave unrecorded units unknown. The image is a designated fallback or image-only representation, not automatically a photograph of a successful print.

All paths in these records are folder-relative paths at their owning snapshot (see Paths). Do not use absolute host paths, external URLs, traversal, or executable sources as artifact references.

For a new component revision, update variant membership and retain old visual bindings until a matching visual is authored. That makes a stale image/assembly explicit instead of silently relabeling it. Matching recorded bindings is not proof of geometric equivalence.

### Production plates and preparation evidence

Each plate has:

| Field | Meaning |
|---|---|
| `id`, `name` | Stable plate ID, unique within the variant, and display name |
| `role` | `production`, `trial`, or `fit-check`; only explicitly selected production plates contribute to the recipe |
| `contents` | Component revisions and per-run quantities |
| `runs` | Authored repeat count, a positive safe integer, or null if not recorded |
| `project_file` | Exact slicer-project path, or null if none is delivered |
| `plate_number` | Optional 1-based positive safe integer selecting the plate within that container |
| `verification` | Preparation receipt for the exact `project_file` bytes, or absent when not verified |
| `layout_revision` | Authored layout revision when available |
| `visual` | Optional `mesh`, `image`, `units`, `members`, and expected `project_sha256` |
| `target` | Recorded `printer`, positive numeric `nozzle_mm`, `material`, `build_plate` and `preset_id`; unknown fields remain absent |

A `contents` entry has `part_id`, `revision`, `quantity`, optional `mesh`/`sha256`, and optional `receipt_sources` (zero-based indices into that plate's referenced receipt `sources` array). Required member quantities, per-run content quantities and run counts are different facts. Two plate IDs may share one `project_file`; the file is not plate identity.

Read the actual preparation receipt before writing contents. Reuse source hashes and input-instance counts; do not ask the user to retype them. The author still selects the production role, required composition and runs. Write the derived quantity into the record and retain its receipt-source binding so the reader can check it.

Map each source entry to an exact component revision. Hash equality establishes equal bytes, not logical identity: identical components may have different IDs. Use explicit `receipt_sources` for ambiguous equal-byte candidates; do not guess by basename. Indices must be in range and cannot be assigned to two contents entries on the same plate. Record unaccounted inputs instead of silently dropping them.

The current Bambu helper requires distinct input files with distinct case-insensitive stems and verifies one plate per invocation. For repeated instances, retain uniquely named immutable copies of the prepared mesh, then bind their source entries to one logical component. Copies are instances/representations, not additional BOM members. Record manually authored multi-plate containers explicitly; do not claim that the single-plate helper produced them.

A manually combined container is a new preparation. Keep its exact `project_file` and plate selectors, but do not attach single-plate receipts as verification of the combined bytes. Retain those original receipts separately and leave the combined container's `verification` absent until that container is actually checked. Never edit a receipt hash to make it match a different delivery.

The receipt's `project_sha256` binds the delivered project bytes. A reader distinguishes authored declarations, receipt-linked claims, actually inspected matching bytes, mismatches and unresolved bindings. A metadata-only read cannot claim it rechecked bytes. Keep original receipts; normalized summaries must allowlist facts and omit host paths/commands, not copy the raw receipt.

Neither receipt matching nor quantity arithmetic proves exported-mesh equivalence inside a 3MF, collision safety, support coverage, physical fit or strength. A changed project-file hash records a changed preparation, not necessarily changed geometry. Bounds alone are not a complete layout fingerprint.

## Scoped work and completion

`work.steps` is the existing project's lightweight roadmap, not a second task database. Each step has an `id` unique within `work.steps`, `title`, `state` (`pending`, `in_progress`, `blocked`, `complete`, `skipped`), optional `kind` (`digital`, `physical`, `general`), `details`, `blocker`, `blocked_by` step IDs, `scope`, and `results`. `work.next_step_id` refers directly to one step or is null. Keep the root free-text `next_action`; do not infer semantic agreement from similar wording.

A scope is null for project-wide work, or an object with `outcome_id`, optional `variant_id`, optional `entity_kind` (`assembly`, `plate`, `model`), and `entity_id` when appropriate. Planned work can name the current logical target. Prefer the exact target `commit` for completed results. Physical results require it: matching some input files cannot bind the observed build's composition, process and conditions to a later version.

Digital input checks can instead retain `input_hashes` entries with folder-relative `path` and `sha256`. They must cover all inputs of their scope: the selected model's mesh; a plate's constituent meshes and delivered project (or designated layout when no project exists); or all required models and production inputs for a whole outcome. An assembly check also binds its designated representation. These paths must identify artifacts of the selected outcome, not unrelated matching files retained elsewhere. Hash-bound applicability remains unresolved until the reader actually inspects and matches those bytes; a metadata-only/offline report must not treat a declared hash as verification. Hashes do not establish unchanged authored quantities or manufacturing conditions; use the commit for version-bound decisions.

Each result has a `summary`, `status` (`passed`, `failed`, `not_checked`, `reported`), optional `recorded_at`, its own `scope`, and `evidence`. Each evidence reference has a folder-relative `path` and optional same-repository full `commit`; absent commit means the evidence belongs to the record's own snapshot, not the older target snapshot.

Keep results and their target bindings when reopening a step; append the new result rather than overwriting earlier completion evidence. A later observation can target an immutable printable version without changing that version's model/plate definition. Do not inherit a newly changed step scope onto old results.

Missing evidence means author-reported completion. Missing physical observations mean untested physical behavior. An STL-only requested handoff can be digitally complete without a slicer project or physical print. Record gaps as gaps, not invented tasks, dependencies or instructions.

### Maintain records where facts become known

| Gate | Record action |
|---|---|
| Design agreement | Establish outcome/variant IDs, intended membership, requested outputs and known work |
| Model export | Record exact part revision/mesh references; bind or mark stale the assembly representation; list reviewed design views in `renders` with their `design_revision` |
| Plate preparation | Read receipt inputs/counts; record stable plate ID, explicit role, source mappings, target and runs |
| Delivery | Commit the verified definition/assets before designating its immutable printable reference |
| Session handoff | Update current states, next action/step and blockers; retain prior result bindings |
| Physical feedback | Append the identified observation with its exact target and conditions; reopen only affected work |
