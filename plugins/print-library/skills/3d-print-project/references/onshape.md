# Onshape modelling recipe

## When to take this branch

Use Onshape for an explicitly requested editable cloud deliverable, revisions to an existing authoritative Onshape model, or an agreed modelling backend. Do not make it a prerequisite for an otherwise complete STL-only request. If it is the backend, create/verify the model before STL export rather than modelling locally first by default.

Record the branch decision and required capabilities before cloud writes. When bringing an existing mesh into an editable model, distinguish a mesh import from an actual parametric reconstruction; compare critical geometry and produce new verified exports before changing the source of truth. A cloud feature that compiles but has not been geometrically checked does not satisfy this stage.

## Connection and authority

Use the official FeatureScript MCP when it is connected. Read the actual exposed tool schemas; do not assume an export, document-management or target-workspace operation exists. Its endpoint is `https://fs-mcp.labs.onshape.app/mcp` with HTTP transport and OAuth.

Check existing MCP configuration before adding another entry. A definition can be project-scoped; OAuth credentials remain in the client credential store. For OMP, user actions `/mcp reload`, `/mcp reauth onshape`, and `/mcp test onshape` can complete setup. Never ask for a password or token in chat, or reset working authentication merely to test it again.

Inform the user before server use: calls consume their Onshape API allocation and exhaustion blocks further requests. Check headroom before a substantial batch; avoid repeated polling. Do not change which account pays for API usage without explicit permission. Free-plan documents are public; establish privacy requirements before creating or sharing CAD.

## Model construction

1. Read saved FeatureScript notes before authoring. Preserve an existing file's language/library version; for new files discover the current `libraryVersion` with a trivial `test_featurescript` lambda. Do not hard-code the pilot's old version as a permanent default.
2. Use explicit units and named parameters. Set defaults using the second map argument to `defineFeature`; missing defaults can prevent tool execution. Separate finished shelf/interface dimensions from clearances.
3. Use `test_feature` for full Feature Studio compilation and actual geometry evaluation. A `test_featurescript` lambda is useful for targeted evaluation and error diagnosis, but does not prove the complete feature's annotations and defaults compile.
4. Test measurable geometry and a meaningful parameter change. FeatureScript's `box` is not a safe local variable name: use a name such as `measuredBounds`. A generic "no features found" response can hide a compiler error; do not assume changing the version is the fix.
5. For a new persistent model, call `create_geometry` only after testing, with `clean: false` when retaining the requested model. It creates a new workspace; capture the returned IDs and link immediately. Review its actual CAD images.
6. For revisions, use the recorded existing document/feature. Read current cloud source and preserve user edits; a whole-Feature-Studio write is destructive. Establish an appropriate version/checkpoint before a consequential update. Do not recreate the whole document just because it is easier.
7. Store a local source snapshot and verification evidence tied to the cloud revision. Where a revision ID cannot be obtained, record that limit rather than inventing one.

A custom feature is parameter-editable native CAD, not a conventional tree of separate standard sketches/extrudes/fillets. If the user needs that tree, discuss the different integration before proceeding. Importing STL does not recover design history.

## Export handoff

The tool set verified in the controller-support pilot had no STL export operation. Re-check capabilities when relevant; do not promise missing automation.

If export remains manual: right-click the actual part in Onshape's Parts list, choose Export, select STL / Binary / Millimeter / Fine, keep "Export models oriented Y axis up" unchecked, and download with a unique project/revision filename. Preserve the raw file. Establish the exact project-specific print transformation separately.

Use the actual download for mesh verification and slicing. Never substitute an earlier local STL and call it an Onshape export. Successful digital mating checks do not establish real insertion force or strength.

**Completion:** deliver the actual requested editable model, link and identifiers, source snapshot/revision evidence, geometry checks and any required exports. If model creation succeeds but export tooling is unavailable, record those outcomes separately and give the precise manual export handoff; never call the entire requested asset delivery complete.

## References

- Setup: https://www.onshape.com/en/blog/get-started-featurescript-mcp-server
- Language/library: https://cad.onshape.com/FsDoc/library.html
- Native feature API: https://onshape-public.github.io/docs/api-adv/featureaccess/
- Export: https://cad.onshape.com/help/Content/File/exporting_files.htm
- API allocation: https://onshape-public.github.io/docs/auth/limits/
