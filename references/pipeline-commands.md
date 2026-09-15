# Stateful Pipeline Commands

Run the bundled `pipeline_runner.py` with its absolute path. The examples below
use `<runner>` as shorthand.

## 1. Start Or Resume

For a new project:

```powershell
python <runner> --project-root . init
python <runner> --project-root . register-research --file <file-1> --file <file-2>
```

`init` installs project-local `PreToolUse` and `Stop` hooks by default. Codex
must review/trust the hook definition before it is active. Use `--no-hooks`
only when the user explicitly declines project hooks.

For every resumed turn:

```powershell
python <runner> --project-root . status
python <runner> --project-root . next
```

## 2. Run Automated Stages

Run only the action reported by `next`:

```powershell
python <runner> --project-root . run-stage
python <runner> --project-root . validate
```

`run-stage` can scaffold the modeling review, validate the reviewed canonical
spec, generate the unified graph, run SHACL/OWL-RL/SPARQL validation, generate
BPMN/OWL, generate `00-07`, or finalize the baseline. It refuses to cross a
human gate.

Requests to continue, skip review, or produce unapproved drafts do not change
the state contract. There is no `--allow-unapproved` command.

Use `--action <expected-action>` when an orchestration system wants fail-closed
protection against stale stage assumptions.

## 3. Human Modeling Approval

Complete `models/review/00-05` first. After a person reviews the named version:

```powershell
python <runner> --project-root . approve `
  --gate modeling `
  --reviewer "<name>" `
  --review-date YYYY-MM-DD `
  --note "<decision and scope>" `
  --human-confirmed
```

The AI must not supply `--human-confirmed` without explicit human approval.

After this gate, compile `models/spec/model-spec.json` with
`meta.review_status` set to `reviewed`, then run the reported automated stage.

## 4. Human Graph, BPMN, And OWL Approval

Review `models/graph`, generated BPMN, and OWL, then complete
`models/review/06-模型审核记录.md`. The record must name RDF/需求图 and BPMN/OWL,
contain the reviewer, and include an `approved` or `通过` conclusion.

```powershell
python <runner> --project-root . approve `
  --gate models `
  --reviewer "<name>" `
  --review-date YYYY-MM-DD `
  --note "<approved scope and conditions>" `
  --human-confirmed
```

The runner verifies that candidate files have not drifted, changes the
canonical spec to `approved`, records review metadata, regenerates and
revalidates the unified graph, and regenerates BPMN/OWL so all trace metadata
matches the approved source.

## 5. Controlled Revision

Never edit an approved or generated artifact directly. Move the state backward:

```powershell
python <runner> --project-root . reopen `
  --to modeling_scaffolded `
  --reason "<change request>"
```

Allowed targets:

- `initialized`: replace or add research sources.
- `research_registered`: recreate modeling scaffolds.
- `modeling_scaffolded`: revise modeling Markdown and repeat human approval.
- `modeling_review_approved`: revise/recompile the canonical spec.

Downstream files remain on disk for comparison but are stale until regenerated.

## 6. Final Acceptance

The final sequence is:

```powershell
python <runner> --project-root . run-stage
python <runner> --project-root . validate
python <runner> --project-root . status --json
```

Only `current_stage: development_ready` with `valid: true` is an accepted AI
development-input baseline.

## 7. Diagnostic Commands

Only these lower-level validators may be called for diagnosing a failed stage:

- `validate_model_spec.py`
- `validate_graph_engineering.py`
- `validate_model_artifacts.py`
- `validate_traceability.py`

All generation and baseline commands are runner internals and must not be
called directly.

Run the skill regression test with:

```powershell
python scripts/self_test.py
```
