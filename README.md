# PaperLab

A virtual lab for reproducing research papers. Part of [Scholar](https://github.com/ashleycribb/s3a-storage), built to feed the S3A Scholar pack.

For a paper the researcher has selected, PaperLab works out:

- **Environment** — software, packages and versions, datasets with links and licenses, hardware, settings and hyperparameters.
- **Run guide** — numbered steps from the paper's methods section that a graduate student can follow.
- **Expected results** — every reported number, table and figure, each with its page or section.
- **Existence checks** — automated verification that things exist, with evidence URLs.

Two audiences: **students** learn by running the experiment themselves; **professors** get records of what was run, what came out, and how it compares to the paper.

## Hard rules (enforced in code)

PaperLab is opinionated software:

1. **The AI only checks whether things exist. People make the judgments.** The CLI blocks any output claiming a paper "reproduces", "is correct", or "is valid" (`paperlab.rules.guard_output`).
2. **Every environment item and step is stated-in-paper (quoted, with page) or inferred (needs human confirmation).**
3. **Every claim gets a verifiable link or page/section reference.** Missing things are marked `not stated`, never guessed silently.
4. Open-access papers only. Dataset licenses are respected and recorded.
5. No GPL/AGPL code copied into deliverables; MIT/Apache-2.0 tooling preferred. No secrets or API keys in outputs.

The only verdict field in the whole system lives on the run record and requires a human signature.

## Quickstart

```bash
pip install -e .            # or: pip install -e ".[dev,signing]"
paperlab init cases/my-paper          # scaffold a new case
paperlab fetch-pdf cases/arxiv-1703.05175 --extract

# Core step, on the bundled case:
paperlab check cases/arxiv-1703.05175   # existence checks (network) -> existence_checks.json
paperlab verify cases/arxiv-1703.05175  # verify expected results vs the paper (presence + pairing)
paperlab diff cases/arxiv-1703.05175 my_run.json   # compare a student's run -> run_record.json (verdict: UNSET)
paperlab records cases/arxiv-1703.05175  # emit versioned, signable record objects
```

`my_run.json` is produced automatically by the capture harness:

```bash
paperlab capture cases/arxiv-1703.05175 --hash-dir data/omniglot \
  --results-file results.json -- python scripts/train/few_shot/run_train.py
```

`capture` wraps the student's commands and records what was **actually** run: exact commands with exit codes, timestamps, durations, and content-hashed logs (`run_logs/`); the real environment (OS, CPU, RAM, GPUs, Python, full `pip freeze`, git HEAD of the code checkout); and SHA-256 pins for dataset directories. Environment variables are never captured, and log text is scanned and redacted for credential patterns before being written. The output passes the verdict guard before it is written. `diff` then computes deltas and within-CI flags, and writes a run record whose `human_verdict` is null until a professor fills and signs it.

## The bundled case

`cases/arxiv-1703.05175` — [Prototypical Networks for Few-shot Learning](https://arxiv.org/abs/1703.05175) (Snell, Swersky, Zemel, NeurIPS 2017). Chosen because it is open access, has official MIT-licensed code, an MIT-licensed dataset (Omniglot), CPU-scale training, and tabulated results with confidence intervals.

The case contains the four PaperLab outputs (`environment.yaml`, `run_guide.md`, `expected_results.json`, `existence_checks.json`) plus:

- `checklist.json` — machine-readable existence checks (URLs, PyPI, quotes, values).
- `table_layouts.json` — the geometry of each PDF table (pdftotext cell order), enabling full 79/79 metric-to-value pairing verification.
- `paper_text/` — cached per-page text extraction of the arXiv v2 PDF (13 pages), so `verify` works offline.

Current verified state: 79 reported results extracted (Tables 1–6), 79/79 presence-verified and 79/79 pairing-verified against the PDF; 27 automated existence checks; 6 items flagged needs-a-human (PyTorch version strategy, training budget, torchnet license, miniImageNet data licensing, statistical comparison policy, final verdict).

## Case layout

```
cases/<paper>/
  case.json               paper metadata + scope + selection rationale
  environment.yaml        every dependency/dataset/hardware/setting, provenance-marked
  run_guide.md            numbered steps linked to methods text
  expected_results.json   {metric, value, table_or_figure, page, quote} per result
  checklist.json          machine-readable existence checks
  table_layouts.json      per-table cell geometry for pairing verification
  paper_text/pageNN.txt   cached PDF page text (offline verify)
  run.json                (student's measured results, after a run)
  run_record.json        (comparison + null verdict, after diff)
```

## Records and Scholar/S3A integration

Each output maps to a versioned, signable record (`paperlab.records`), aligned with the S3A Scholar pack primitives: `quote_sha256` + `passage_page` anchoring (ScholarNoteClaimRecord), dual-trace human/AI provenance (HumanLrsRecord / AiTraceRecord), Ed25519 signing (s3a-vault identities), and Merkle-sealed version history (s3a-vcs). See `docs/design.md`.

## Status and roadmap

- [x] Prototype case: full environment/run-guide/results/checks for arXiv:1703.05175
- [x] CLI: init / fetch-pdf / check / verify / diff / records
- [x] Verdict guard: AI verdict claims blocked in code (object-level, not just serialized text)
- [x] Run-capture harness: wraps commands, snapshots the actual environment, hashes datasets, redacts secrets
- [ ] S3A pack integration (write records into a live S3A archive)
- [ ] Second case (candidates welcome)

## License

MIT. PaperLab contains no code from the papers it reproduces; paper PDFs are fetched at runtime and never committed.
