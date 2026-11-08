from __future__ import annotations

from .forums import COUNTY_ADAPTERS, PROCEEDINGS, forum
from .rules import RULES, cost_of_sale, deadlines_for, exchange_due, matrix_markdown, remote_upload_due, rules_for

STATE = "FL"
RULESET = {"id": "fl-vab", "version": "2026-11-07", "checked": "2026-11-07",
           "covers": ["just value petitions to a Value Adjustment Board", "informal conference summaries"],
           "not_covered": ["exemption, classification, portability and deferral petitions", "circuit court actions"],
           "note": "Florida statutes, Department of Revenue rules and forms as amended through 2026-11-02, and the configured county procedures."}

__all__ = ["STATE", "RULESET", "COUNTY_ADAPTERS", "PROCEEDINGS", "RULES", "cost_of_sale", "deadlines_for", "exchange_due", "forum",
           "matrix_markdown", "remote_upload_due", "rules_for"]
