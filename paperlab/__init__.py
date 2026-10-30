"""PaperLab: a virtual lab for reproducing research papers.

Part of Scholar, the doctoral design-based research project built on S3A
(https://github.com/ashleycribb/s3a-storage).

Hard rules (enforced in paperlab.rules):
- The AI only checks whether things exist; humans make the judgments.
- Every environment item and step is stated-in-paper (quoted, with page)
  or inferred (needs human confirmation).
- Every claim carries a verifiable link or page/section reference.
- No verdicts from the AI, ever.
"""

__version__ = "0.1.0"

from . import capture, checks, compare, records, rules, verify  # noqa: F401

__all__ = ["capture", "checks", "compare", "records", "rules", "verify", "__version__"]
