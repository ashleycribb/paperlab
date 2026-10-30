# PaperLab Design Note

PaperLab is the reproduction wing of Scholar, built on S3A ([ashleycribb/s3a-storage](https://github.com/ashleycribb/s3a-storage)). This note covers: (1) how the four prototype outputs become versioned, signed records; (2) what the reproduction record holds after a student runs the experiment; (3) environment-recreation tooling; (4) gaps and risks found while building the prototype.

Paper chosen for the prototype: **Prototypical Networks for Few-shot Learning** ([arXiv:1703.05175](https://arxiv.org/abs/1703.05175)) — open access on arXiv, official MIT-licensed code, MIT-licensed Omniglot dataset, CPU-scale training, and crisply tabulated results. All of these were verified, not assumed (see `existence_checks.json`).

## 1. Four outputs, four record types

S3A's Scholar pack (`crates/s3a-pack-scholar`) already ships the primitives PaperLab needs: `ScholarNoteClaimRecord` carries `citation_fingerprint_id`, `passage_page`, and a SHA-256 `quote_sha256` of the exact quoted passage; `HumanLrsRecord` carries human decisions with an O(1) pointer to the AI trace step that produced them; and the pack has dual-trace provenance and citation-recheck support. PaperLab adds four record types, one per output, all following the same conventions:

- **Ed25519 signatures** via `s3a-vault` identities. Every record is signed by its producer (AI agent or human) and carries the signer's vault identity, so a student can never silently impersonate the professor.
- **Versioning** via `s3a-vcs`: each save is a Merkle-sealed commit on a branch (e.g., `paperlab/1703.05175`), giving content-addressed, tamper-evident history with deterministic merges. The AI never overwrites; it appends new versions, and `recheck` can re-run citation checks against any historical version.
- **Dual-trace linkage**: every AI-generated record stores the `AiTraceRecord` coordinate of the reasoning/extraction step that produced it (the pack's `STEP_CLAIM`/`STEP_TOOL_CALL` categories), and every human confirmation stores a `HumanLrsRecord` pointing back at it.

| Output file | Record type | Key fields (extending Scholar pack types) |
|---|---|---|
| `environment.yaml` | `PaperLabEnvironmentRecord` | `paper_fingerprint_id`, items[] each with `provenance` (stated_in_paper / stated_in_repo / inferred / not_stated), `quote_sha256`, `passage_page`, `evidence_url`, `check_ids[]` pointing at existence-check records, `human_confirmation` (null until a HumanLrsRecord signs off) |
| `run_guide.md` | `PaperLabRunStepRecord` | `step_no`, instruction text, `quote_sha256` + `passage_page` of the methods text it implements, `command`, `evidence_url` |
| `expected_results.json` | `PaperLabExpectedResultRecord` | `metric`, `value`, `table_or_figure`, `passage_page`, `quote_sha256`, `paper_fingerprint_id` — one record per extracted value (79 for this prototype) |
| `existence_checks.json` | `PaperLabCheckRecord` | `item`, `check`, `result`, `evidence_url`, `checked_at`, `agent_id`, plus a companion `needs_a_human` queue that mints `ask_human` clearance gates (the `s3a-harness` already implements this gate type) |

Crucially, the schema enforces the hard rule: no record type has a "reproduces" or "valid" field for the AI to fill. The only verdict field lives on the reproduction run record (below) and requires a human signature.

## 2. The reproduction run record

After the student runs the experiment, PaperLab writes a `PaperLabRunRecord` linked to specific **versions** of the four records above (content hashes, not "latest"):

```
run_id: UUID
paper_fingerprint_id: 1703.05175v2
environment_record: <s3a-vcs commit hash>
expected_results_record: <s3a-vcs commit hash>
run_guide_record: <s3a-vcs commit hash>
what_was_run:
  commands: [exact commands with flags]
  git_commit_of_code: <hash of jakesnell/prototypical-networks>
  started_at / finished_at
  training_budget: episodes or epochs actually run (and whether early stopping fired)
environment_actually_used:
  os / cpu / gpu (from /proc, nvidia-smi)
  pip freeze / conda list export (the real versions, not the planned ones)
  dataset snapshot hashes: SHA-256 of the two Omniglot zips
outputs:
  logs: tile-addressed log records
  measured: [{metric, value, episodes_evaluated, confidence_interval_if_any}]
comparison:
  per metric: {paper_value, measured_value, delta, within_paper_ci: true/false/null}
  computed arithmetically by PaperLab — presented, never judged
human_verdict:            # THE FIELD THE PROFESSOR FILLS IN
  verdict: null          # enum: supports | partially-supports | does-not-support | inconclusive (null until signed)
  notes: null
  professor_identity: null  # s3a-vault Ed25519 identity
  signed_at: null
  decision_score: null   # HumanLrsRecord field
```

The comparison block is deliberately mechanical: deltas and within-CI booleans only. The professor reads the evidence and signs the verdict; that signature is a `HumanLrsRecord` with a verb like `decided`, tied through the dual-trace pointer to the run record it judges.

## 3. Environment-recreation tools

| Tool | Role | License |
|---|---|---|
| Docker | Primary prototype path: pinned image (`python:3.6-slim` + verified wheels), one command to share with students | Apache-2.0 |
| Apptainer/Singularity | Same container, HPC-friendly (no daemon, runs unprivileged on university clusters) | BSD-3-Clause |
| Nix / flakes | Gold standard for bit-reproducible environments; best fit for S3A's determinism ethos; package set is MIT (the Nix evaluator itself is LGPL-2.1 — usable, not copyable) | LGPL-2.1 (Nix), MIT (nixpkgs) |
| conda / micromamba | Fast for the Python 3.6 pin this repo needs; watch Anaconda's commercial ToS for institutional use | BSD-3 / MIT (mamba) |
| uv / pip | Wheel-level pinning inside any of the above; `uv` is Apache-2.0 | Apache-2.0 / MIT |

Recommendation: Docker (or Apptainer on HPC) with a `requirements-lock.txt` captured by the student at run time, all hashed into the run record. Nix flake as a stretch goal for full bit-reproducibility. All listed tools are permissive-licensed; no GPL/AGPL code is copied into any deliverable. The pinned runtime itself (PyTorch 0.4, BSD-3) is fine to use; torchnet's NOASSERTION license is flagged for human review.

## 4. Gaps and risks found

1. **Ephemeral dependency chain (highest risk).** The repo's tested stack (Python 3.6, PyTorch 0.4) is 2018-era. PyTorch 0.4 is gone from PyPI; only the official CPU wheel still resolves (verified). GPU wheels for CUDA 8/9 will not run on modern drivers. Any reproduction therefore involves a human decision (CPU-only, or adapt the code) — and code adaptation weakens the "same experiment" claim. PaperLab surfaces this rather than hiding it.
2. **Missing specification in the paper.** Total training episodes, stopping rule, random seed, and hardware are not stated anywhere in the paper; only the repo's defaults fill the gap, and they are choices, not paper statements. Without a seed, exact-number equality is impossible; comparison must be statistical (confidence intervals, which the paper helpfully reports for miniImageNet but not Omniglot).
3. **Data licensing asymmetry.** Omniglot is clean (MIT). miniImageNet images are ILSVRC-derived (research-only, non-commercial) and are not even distributed by the official repo — only split CSVs. The CUB zero-shot experiment adds a third data owner. Scope creep here is a legal risk, so the prototype confines the run guide to Omniglot.
4. **torchnet license is NOASSERTION.** It is a required runtime import. Needs human review before institutional deployment.
5. **Version drift.** arXiv v2 vs. the NeurIPS proceedings version may differ in pagination; all quotes in this prototype are anchored to the arXiv v2 PDF (13 pages), and the record's `paper_fingerprint_id` pins that exact artifact hash.
6. **Student-facing risk: false confidence.** A student who gets 98.9% instead of 98.8% may declare victory; the design answer is that the AI never emits a verdict and the professor's signature gate is mandatory before any "reproduction" label is queryable in Scholar.
