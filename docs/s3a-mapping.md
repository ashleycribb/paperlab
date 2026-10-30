# Plan: wiring PaperLab records into the S3A Scholar pack

Status: **plan only, no code.** 2026-10-30. Everything below is verified by reading the files at the cited lines.

- PaperLab = [ashleycribb/paperlab](https://github.com/ashleycribb/paperlab) (private) `master` @ `505362c`. Cited as `PL:path:line`.
- S3A = [ashleycribb/s3a-storage](https://github.com/ashleycribb/s3a-storage) `main` @ `9f441c6`, under `crates/` unless noted. Cited as `S3A:path:line`.
- Builds on `plan-scholar-research-corpus.md` (tiles 128-143, "Checking findings") and `prompt-scholar-snapshot-full-metadata.md` (tiles 128-136, `scholar import`). Neither is merged: `rg paper_meta` finds nothing on `main`, and no remote branch claims 128+.

**Rules honored:** AI checks that things exist; judgments are human. No money/crypto. S3A core is untouched (everything is Scholar pack, `ADDON_EDU`). No secrets in any record.

## 0. What PaperLab actually produces today (read from code)

| Output | Where | Notes (verified) |
|---|---|---|
| `case.json` paper id/title/urls | `PL:cases/arxiv-1703.05175/case.json:1-10` | id is `arXiv:1703.05175v2` (version suffix included) |
| environment (software/datasets/hardware/settings, each with `provenance`) | `PL:cases/.../environment.yaml:34,88,119,142` | only YAML; **no exporter** to records (`EnvironmentRecord.build` exists, `PL:paperlab/records.py:65-75`, but nothing calls it) |
| run guide steps | `PL:cases/.../run_guide.md` | prose; `RunStepRecord` (`records.py:78-94`) never emitted |
| expected results | `expected_results.json` (79 rows: metric, value, table_or_figure, page, quote) | only thing `paperlab records` exports (`PL:paperlab/cli.py:170-184`) |
| existence checks | `existence_checks.json` (**20** checks; 19 pass, 1 `fail (HTTP 404)` = PyPI torch 0.4.0) | README says 27, design.md says 28: counts disagree with the file |
| needs-a-human queue | `needs_a_human.json` H1-H6; also embedded in `existence_checks.json` | H6 = "Final reproduction verdict" (a queue item, not a verdict) |
| run capture | `PL:paperlab/capture.py:215-251` -> `run.json` | `what_was_run.commands[]`, `environment_actually_used` (os, cpu, ram, gpus, python, pip_freeze, git_head, dataset_hashes), `results[]` |
| run record | `PL:paperlab/compare.py:63-85` (via `cli.py:120-141`) -> `run_record.json` | contains `human_verdict {verdict,notes,professor_identity,signed_at}` all null |

## 1. Record-by-record mapping

### 1.0 Shared layout for the new tiles
Follow the step-1 prompt layout (`prompt-scholar-snapshot-full-metadata.md`, Build 1): fixed Pod header + length-prefixed UTF-8 fields, `VARIABLE_PAYLOAD | COPY_THROUGH_COMPACT`, `required_addon = ADDON_EDU`, written via `write_raw_hyper_tile` (`S3A:s3a-engine/src/lib.rs:809`), registered in `register_pack_types` (`S3A:s3a-pack-scholar/src/pack.rs:169`). Common header fields: `paper_id u64`, `record_kind u16`, `flags u16`, `seq u32`, `field lengths`, `payload_sha256 [u8;32]` (dedupe key), `supersedes [u8;32]` (zero = none), `producer_id u64`, `producer_kind u8` (1 human, 2 agent), `crc32c`.
**`payload_sha256` is computed by the importer over `{record_type, payload}` only** (see gap G3: PaperLab's own `content_sha256` includes `created_at`, `PL:records.py:47,58-62`).

### 1.1 Tile allocation (inside the planned 128..=147 band)

| Tile | Name | Source | Status in plan |
|---|---|---|---|
| 128 | `paper_meta` | case.json paper block | planned (step 1) |
| 129 | `paper_pdf_ref` | PDF url + SHA-256 | planned (step 1) |
| 134 | `paper_version` | `v2` from the paper id | planned (step 1) |
| **139** | `paper_methods_env` | **environment items + run-guide steps** | already claimed in plan table ("what PaperLab needs, stated vs inferred") |
| **141** | `paper_exception` | **needs-a-human H1-H6** | already claimed ("items for the human queue") |
| **144** | `paperlab_check` | existence checks | **new** |
| **145** | `paperlab_expected` | expected results | **new** |
| **146** | `paperlab_run` | run capture + mechanical comparison | **new** |
| **147** | `paperlab_decision` | signed human decisions incl. the verdict | **new** (modelled on tile 96) |

Not used on purpose: 135 `paper_verification` (that is "the authors' own verification folder", openai/math style; mixing a student's rerun there would put two different things behind one "recorded status" field), tile 20 (researcher notes are never overwritten and must not fill with machine-extracted rows), tile 10 (consent-gated, see 3.2).

### 1.2 Paper identity -> 128 / 129 / 134
| PaperLab field | Tile field | Cites |
|---|---|---|
| `paper.id` `arXiv:1703.05175v2` | split: `arxiv_id=1703.05175` (new match key, G5) + `version_key=v2` -> 134 | `PL:case.json:3`, `PL:environment.yaml:18-19` |
| `paper.title`, `authors[]`, `venue` | 128 `title`, `authors`, `venue` | `PL:environment.yaml:20-23` |
| `paper.url`, `pdf_url` | 128 OA links; 129 location | `case.json:5-6` |
| license text | 128 `license_class` (see G7) | `environment.yaml:24` |
| sha256 of `paper.pdf` | 129 `sha256` | **not recorded anywhere today** (`PL:cli.py:65-78` downloads, never hashes; design.md:77 says it pins the hash). PaperLab change needed (PR P1) |

### 1.3 Environment + run steps -> 139 `paper_methods_env`
One record per item; `item_kind`: 1 software, 2 dataset, 3 hardware, 4 setting, 5 run_step.
| PaperLab field | 139 field | Cites |
|---|---|---|
| `name` / `item` | `name` | `PL:environment.yaml:35-86` |
| `version`/`value` | `value` (text as stated) | same |
| `provenance` stated_in_paper / stated_in_repo / inferred / not_stated | `provenance u8` 1..4 (same vocabulary) | `PL:rules.py:147-150` |
| `quote` + `page` | `quote_sha256 [u8;32]`, `passage_page u32`, `passage_char_offset/length` (same semantics as `ScholarNoteClaimRecord`) | `S3A:records.rs:100-122` (fields 72-120 of the struct); `PL:records.py:84-94` |
| `evidence_url`, `evidence` text | `evidence_url`, `evidence` | `environment.yaml:41-45` |
| `note` | `note` | `environment.yaml:46,52-60` |
| step `command`, `step_no`, `text` | `command`, `seq`, `text` (item_kind 5) | `PL:records.py:84-94` |
| `HUMAN_NEEDED` flag = provenance in `NEEDS_HUMAN_PROVENANCE` | **derived at read time**, not stored | `PL:rules.py:153-157` |
| `human_confirmation` (design.md:17) | **not a field here**: a signed 147 record of kind `item_confirmation` pointing at the item's `payload_sha256` | see 3 |
The raw `quote` text is **not** stored (only its hash + page + offsets), same as `CitationFingerprintRecord` stores no copyrighted payload (`S3A:records.rs:851-853`). Quote text stays in the researcher's case folder or `paper_section` (130) when license allows.

### 1.4 Existence checks -> 144 `paperlab_check`
| PaperLab field | 144 field | Cites |
|---|---|---|
| `item` | `item` | `PL:existence_checks.json` (checks[]) |
| `check` (text, may say "expected: fail") | `check` (verbatim) | `PL:checks.py:135` |
| `result` (`pass` / `fail (HTTP 404)` / `pass (latest only)` / ...) | `result_code u8` (1 pass, 2 fail, 3 other) **plus** `result_text` verbatim | `PL:checks.py:35-50,76,83,129` |
| `evidence_url` | `evidence_url` | same |
| `checked_at`, `checked_by` | `checked_at`, `producer_id` = `hash_iri("paperlab-cli")` | `S3A:xapi.rs:293`; `PL:cli.py:175` |
A `fail` is stored as "the thing was not found", which is an existence outcome. The importer never stores or computes an "expected vs actual" flag; the "expected: fail" wording stays inside `check` text only. Re-running checks later makes a **new** record (new `checked_at`), never an overwrite.
`verify_report.json` (79/79 presence and pairing) -> two summary records in 144 (`check="verify presence"`, total/passed counts, `evidence_url=paper pdf url`), same existence-only semantics (`PL:verify.py:32-98`).

### 1.5 Expected results -> 145 `paperlab_expected`
| PaperLab field | 145 field | Cites |
|---|---|---|
| `metric` | `metric` | `PL:records.py:102-111`; `expected_results.json` |
| `value` (`98.8%`, `54.60 ± 0.62%`) | `value_text` verbatim + parsed `point f64`, `ci f64` (NaN = none), `unit u8` | parse rule `PL:compare.py:13-23` |
| `table_or_figure` | `table_label`; `table_record_key` -> tile 132 row (zero until 132 is filled by extraction) | `S3A` plan 132 |
| `page` | `passage_page` | |
| `quote` | `quote_sha256` + offsets (text not stored, as 1.3) | |
| `verify` presence/pairing outcome per row | `found_on_page u8`, `paired u8` (0 unknown, 1 yes, 2 no): mechanical | `PL:verify.py:32-90` |
`qualitative_figures` (Figure 2, 3) -> tile 131 `paper_figure` when that exists; not in 145.

### 1.6 Needs-a-human -> 141 `paper_exception`
| PaperLab field | 141 field |
|---|---|
| `id` H1-H6 | `item_key` |
| `item` | `title` |
| `why` | `reason` |
| `evidence_url` | `evidence_url` |
| (new) | `state u8`: 1 open. **The importer only ever writes `open`.** Only a signed 147 record can resolve an item; "resolved" is derived by joining 147 on `item_key`. |
H6 is imported like the others and stays open until a signed verdict (147 kind 1) exists for a run of this paper.

### 1.7 Run record -> 146 `paperlab_run` (+ blobs)
Input is `run.json` + `run_record.json`. One 146 record per run.
| PaperLab field | 146 field | Cites |
|---|---|---|
| `captured_at`, `captured_by` | `captured_at`, `producer_id` (=`paperlab-capture`) | `PL:capture.py:241-243` |
| run identity | `run_id [u8;16]` = first 16 bytes of `payload_sha256` | G3 |
| `paper_id` | header `paper_id` (see 2) | `PL:compare.py:73` |
| `environment_record` / `expected_results_record` / `run_guide_record` hashes | `env_set_hash`, `expected_set_hash`, `guide_set_hash` = hashes of the sorted `payload_sha256` lists of the 139/145 records the run was compared to | `PL:records.py:144-155`, G4 |
| `what_was_run.commands[]` (`command[]`, `cwd`, `exit_code`, started/finished/duration) | `commands[]` same fields | `PL:capture.py:171-208` |
| `logs.stdout/stderr {path, sha256, bytes}` | `sha256`, `bytes` + blob ref into tile 24 (log text is already redacted at capture) | `capture.py:184-203`; core blob tile `S3A:s3a-core/src/lrs.rs:15` |
| `stdout_tail/stderr_tail` | not stored (they are in the log blob) | `capture.py:202-203` |
| `stop_on_failure`, per-command `note` | `stop_on_failure`, `note` | `capture.py:205-207,244-247` |
| `environment_actually_used`: kernel, machine, os_*, cpu, cpu_count, ram_total_kb, gpus[], python, executable, git_head | typed fields, text verbatim | `capture.py:71-141` |
| `pip_freeze[]` (or `packages[]` fallback) | `packages[]`, sorted, `source u8` (pip/importlib) | `capture.py:120-131` |
| `dataset_hashes` | **`dataset_manifest_sha256`, `total_files`, `total_bytes` only**; full manifest -> tile 24 blob (G6) | `capture.py:144-159` |
| `results[]` / `outputs.measured[]` `{metric,value,episodes_evaluated}` | `measured[]` | `PL:compare.py:77`, `capture.py:249` |
| `comparison.rows[]` `{metric,paper,measured,delta_pp}` | `delta_rows[]`: `metric`, `paper_point`, `measured_point`, `delta_pp` (numbers only) | `PL:compare.py:44-56` |
| `comparison.missing_metrics[]` | `missing_metrics[]` | `compare.py:57` |
| `comparison.rows[].within_paper_ci` | **not stored** (open question Q3): "close enough" is policy item H5, a human call | `compare.py:45-52`; `needs_a_human.json` H5 |
| `human_verdict {...}` | **dropped and never written**; must be all-null or the file is refused | `PL:records.py:160`, `compare.py:79-84` |
No `status`, `ok`, `matches`, `reproduces`, `consistent` or `valid` field exists in 146. Exit codes stay as observations about commands.

## 2. Linking a run to the paper in the one main database
- **Key:** PaperLab id `arXiv:1703.05175v2` -> normalize (strip `arXiv:` and `vN`, lowercase) -> `1703.05175`; DOI form `10.48550/arxiv.1703.05175`. Verified: OpenAlex returns `doi = https://doi.org/10.48550/arxiv.1703.05175`, id `W2601450892`, `is_oa: true`, `oa_status: green` ([api.openalex.org](https://api.openalex.org/works/doi:10.48550/arXiv.1703.05175)); its `ids` has no arXiv field, and its `license` is null on all locations.
- **Match order** (extends step 1's "normalized DOI or OpenAlex id"): normalized DOI (arXiv DOI form) -> OpenAlex id -> `arxiv_id`. A match reuses main's `paper_id`; no match creates a minimal 128/134 stub (title, arxiv id, version) flagged `from_paperlab`, so records are never orphaned and a later OpenAlex download merges by the same keys.
- **`paper_id` function:** today FNV-1a of the *raw* DOI string, un-normalized (`S3A:s3a-cli/src/main.rs:4122-4140`; `hash_iri` `S3A:xapi.rs:293`). The shared helper from step 1 must normalize first (lowercase, strip `https://doi.org/`), else `10.48550/arXiv.1703.05175` and `10.48550/arxiv.1703.05175` hash differently.
- **Version:** `v2` goes to 134; all 144/145/146 rows carry the version key they were anchored to (quotes are anchored to arXiv v2, 13 pages, `PL:design.md:77`). A run is linked to expected results by `expected_set_hash`, not by "latest".
- **Many runs per paper** are normal: every 146 has its own `run_id`; the join is `paper_id -> runs -> decisions`.

## 3. The human verdict: signed human record, no AI-writable verdict

### 3.1 Design: tile 147 `paperlab_decision`, modelled on tile 96
Tile 96 already is the pattern: a 160-byte record with an Ed25519 signature over `domain tag || bytes 0..96`, key held by the caller/vault, library only verifies, no function that suggests a verdict (`S3A:s3a-pack-scholar/src/committee.rs:1-21,122-134,178-206`; `S3A:docs/SCHOLAR_EXPLORER_S3A_ARCHITECTURE.md:233-272`). 147 reuses that shape with a PaperLab domain tag `S3A-SCHOLAR-PAPERLAB-DECISION-v1\0`:
| Field | Meaning |
|---|---|
| `subject_hash [16]` | tagged hash of `paperlab:<kind>:<target payload_sha256 hex>`, so the signature **binds the exact run/item content** (tile 96's `submission_hash` is only 16 bytes of a hash of an id string, so the id must contain the full content hash) |
| `reviewer_hash [16]` | hash of the vault identity id |
| `comment_hash [16]` | commitment to the human's text (text body kept in tile 143 `note_text` or the researcher app, as tile 96 does) |
| `kind u16` | 1 `run_verdict`, 2 `item_resolution` (H1-H5), 3 `item_confirmation` (env items) |
| `value u32` | kind 1: 1 supports, 2 partially-supports, 3 does-not-support, 4 inconclusive (the exact enum in `PL:records.py:132`); kind 2/3: option index or 1 confirmed / 2 rejected |
| `timestamp_sec`, `layout_version`, `signature[64]`, `prev_hash[32]` | as tile 96 |
**Chain scope:** tile 96 has one global chain per file (`committee.rs:230-244`; wasm delta rejects non-extending chains, `S3A:s3a-wasm-snapshot/src/agent_api.rs:861-875`). That breaks merging two researchers' files. For 147 the chain is **per `subject_hash`** (revisions of one verdict), and merge dedupes by signature bytes (Q4).

### 3.2 Why not tile 10 only
`HumanLrsRecord` has no signature and `object_hash` is 32-bit (`S3A:records.rs:10-19`). Tile 10/11 writes are silent no-ops without an active research consent (`S3A:docs/SCHOLAR_EXPLORER_S3A_ARCHITECTURE.md:225-231`), so a verdict could vanish. Tile 96's doc says why judgments live outside consent gating (`committee.rs:1-6`). A tile 10 mirror (verb `decided`, `ai_trace_coord` to the run's AI trace) is allowed as an optional **derived** copy only when consent is granted; never the source of truth. A new human-only verb takes a free bit in `allowed_verb_mask` (bits 0-26 used, `S3A:xapi.rs:235-237`; 27-31 free) and is **absent from every agent mask** (`S3A:records.rs:577-588`, seeds `751`).

### 3.3 The rule "no AI-writable field can hold a verdict" (enforced in four places)
1. **Types.** 144-146, 139, 141 have no verdict/status/pass field; fields are enums for observations, numbers, hashes, or labelled text (`quote`, `command`, `note`). A schema test fails if a field named `verdict|human_verdict|status|reproduc*|valid*|consistent|ok` appears in those layouts.
2. **One write door.** Only `record_paperlab_decision(rec, reviewer_pubkey)` writes 147: it verifies the Ed25519 signature (like `agent_api.rs:333-358`) and requires `reviewer_pubkey` to be in the researcher's vault identity list with `owner_kind = 1 Person` (`S3A:docs/spec/S3A-VAULT.md:106`). The importer calls the same door; an unsigned or agent-keyed record is rejected and counted (`rejected_unsigned_decision`).
3. **Input refusal.** `import-paperlab` refuses any run file whose `human_verdict` has a non-null field, and never copies `human_verdict`; a 147 record in the input is accepted only through door 2.
4. **Phrase scan = lint only.** Port PaperLab's phrase list as a non-blocking warning count (`PL:rules.py:16-37`); it is not a judge, and the real protection is 1-3 (the guard is regex-based and acknowledged narrow, `rules.py:126-143`).
Backed by the existing invariant: claim support is a non-delegable judgment that agents must route to `ACTION_ASK_HUMAN` (`S3A:docs/spec/S3A-VAULT.md:154-159`).

### 3.4 Keys and signing formats
PaperLab signs canonical JSON with a PEM key via `cryptography` (`PL:records.py:165-187`); S3A signs a fixed binary message. They do not interoperate. Plan: AI records (139-146) are unsigned (their identity is `payload_sha256` + `producer_id` in the agent registry tile 18); **only human decisions are signed, and only in the S3A format**, with the key in the vault (library never holds private keys). PaperLab's JSON signing stays optional for drafts.

## 4. Import path (idempotent)
1. **PaperLab side:** new `paperlab export-scholar <case> --out <dir>` writes `paperlab_export_v1/`: `paper.json`, `environment.jsonl`, `checks.jsonl`, `expected.jsonl`, `needs_human.jsonl`, `runs/<run>.json`, `manifest.json` (file hashes). It reads existing files (no network) and contains no verdict.
2. **S3A side:** new subcommand `s3a-cli scholar import-paperlab <dir> --into <main.s3a> [--json]` beside `ingest/recheck/proof/export-bib` (`S3A:s3a-cli/src/main.rs:1085-1100`), backed by `import_paperlab_into_main(dir, main) -> PaperlabImportReport` in the pack. Parse with `serde_json`; bad lines counted and skipped (no panic on input).
3. **Steps:** validate `manifest.json` hashes -> resolve paper (section 2) -> compute delta **read-only** (key = `(paper_id, kind, payload_sha256)`) -> if empty, do not open main for writing (file SHA-256 unchanged) -> else append only the missing records; never modify/tombstone old ones; a changed re-export adds a record with `supersedes`. Enables `ADDON_EDU` if needed. Report added / skipped-duplicate / rejected per tile.
4. **Snapshots:** tiles 139-147 also ride in snapshot export/intake and in step 1's `scholar import <snapshot>`, deduped by the same keys. Today `SrsSnapshotBundle` has no such fields (`S3A:snapshot.rs:20-33`) and the append-without-dedupe intake stays unchanged (`snapshot.rs:441-470`).

## 5. Gaps and conflicts
- **G1 Tile band policy.** `docs/pack-contract.md:22` and `docs/spec/registry.md:19-20` put 64+ in "third-party / vendor"; Scholar already sits at 96 by amendment (`pack-contract.md:18`). 128-147 needs the same amendment in both docs. Free today: no tile 128+ is used in `main`; `112-115` belong to s3a-events (`/workspace/s3a-events/src/lib.rs:14-17`); `100-102` appear only in registry unit tests (`S3A:s3a-core/src/registry.rs:1080-1108`).
- **G2 Gates keyed to ranges.** `ScholarPack::tile_range` is `10..=32` (`pack.rs:192-194`, already misses 96) and the no_std `required_addon_for_tile` hard-codes `10..=15 | 18 | 20` (`S3A:s3a-core/src/lib.rs:291-307`), so 96 and 128+ are gated only through the std registry. wasm delta apply rejects unknown tile types (`agent_api.rs:840-856`). Each new tile must be added to those lists, or PaperLab tiles cannot travel in wasm snapshots.
- **G3 Not idempotent today.** PaperLab `content_sha256` includes `created_at` (`records.py:47,58-62`). Checked: two identical `ExpectedResultRecord`s built a second apart have different hashes. Importer must hash `{record_type,payload}` only.
- **G4 Design vs code drift.** design.md promises `quote_sha256`, `paper_fingerprint_id`, `check_ids[]`, `human_confirmation` (`design.md:17-20`); code stores raw `quote`, none of the others (`records.py:102-126`). `cmd_diff` emits a plain dict without the three input-set hashes (`compare.py:63-85`). `paperlab records` exports only expected results (`cli.py:170-184`). Fix in PaperLab first (P1).
- **G5 No arXiv match key** in the planned tile 128 field list; OpenAlex gives only the arXiv DOI (checked above).
- **G6 Size.** One tile payload is 130,560 B (`S3A:s3a-core/src/lib.rs:73`). Omniglot hash-dir output is about 32k files (964+659 characters x 20 images, estimate) = several MB as JSON, so it cannot sit in one record. Hence manifest hash + counts in 146 and the full manifest as a tile 24 blob. The 79 expected rows (~50 KB) and 20 checks (~6 KB) each fit one tile.
- **G7 License class.** OpenAlex gives `license: null` for this arXiv paper; plan section 3 treats unknown as closed and "exports refuse text tiles unless `license_class=open`". PaperLab stores only hashes/offsets (no quote text), so it is unaffected; but `paper_text/` in the repo is a separate, already-flagged redistribution issue.
- **G8 Vault cannot say "human" by itself.** `owner_kind` exists (`S3A-VAULT.md:106`) but nothing in the pack checks it today; door 2 must.
- **G9 Registry drift to avoid copying.** descriptors say `record_size: 64` for tile 15 and 20 (`pack.rs:107,133`) though the structs are 512 B and 160 B.
- **G10 Agent registration.** `paperlab-cli` needs a tile 18 `AgentRegistryRecord` (kind verifier, no human-verdict verb); none exists (`records.rs:751`).
- **G11 Counts.** README/design state 27/28 checks; the file has 20 (19 pass). Reconcile before the first import report is quoted anywhere.

## 6. PR breakdown (one PR each, branch from and target the repo's default branch; Ashley merges)
PaperLab (default branch is `master`; rule says `main`, so rename first):
- **P1** `paperlab export-scholar`: `paperlab_export_v1`; fix G3/G4 (stable payload hash, quote_sha256, set hashes, hash `paper.pdf` in `fetch-pdf`, env/step/check exporters). Tests: export twice -> byte-identical; no `human_verdict` in output.
- **P2** reconcile check counts in README/design (G11) and document the interchange format.

S3A (depends on step 1 = tiles 128-136 PR landing first):
- **S1** Docs: amend `pack-contract.md` / `registry.md` for 128-147 (G1); no code.
- **S2** Register tiles 139, 141, 144, 145, 146 (+ gates in G2), layouts and round-trip tests; schema test for 3.3(1).
- **S3** `import-paperlab` + `PaperlabImportReport`; paper resolution with arXiv key (G5); idempotency and unchanged-SHA test; tile 24 blob for manifests (G6).
- **S4** Tile 147 `paperlab_decision` + `record_paperlab_decision`, vault `owner_kind` check, agent-mask exclusion, tests: unsigned/agent-key/null-verdict-in-run rejected, tamper breaks signature, merge by signature.
- **S5** Snapshot export/intake and wasm delta carry 139-147.
- **S6** `s3a-cli inspect` section "PaperLab runs per paper" (counts, run ids, open H items, latest signed verdict if any).
Acceptance for S3/S4 (evidence in each PR body): import the 1703.05175 case twice -> second report all-zero and `sha256sum main.s3a` unchanged; 79 expected, 20 checks, 6 open exceptions, 1 run; `rg human_verdict` finds no write path; a hand-built unsigned verdict is refused.

## 7. Open questions for Ashley
1. OK to claim 128-147 for the Scholar pack (needs the G1 doc amendment), with 144-147 as the new PaperLab tiles?
2. Verdict enum: keep PaperLab's four values (supports / partially-supports / does-not-support / inconclusive) in tile 147, rather than reusing tile 96's approve/revise/reject?
3. Store `within_paper_ci` at all? I recommend deltas only, because "close enough" is policy item H5 (a human call).
4. Per-subject hash chain for 147 (merge-friendly) instead of tile 96's one chain per file?
5. Run logs and dataset manifests into core tile 24 blobs, or inside the pack?
6. Rename PaperLab `master` -> `main` before P1/P2?
