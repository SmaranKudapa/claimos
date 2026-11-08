from __future__ import annotations

import datetime as dt
import hashlib
import json
from dataclasses import dataclass, field

RESULT_SCHEMA = "claimos.evidence.result/1"
INPUT_SCHEMA = "claimos.evidence.input/1"
METHOD_VERSION = "fl-sales-comparison/1"

APPEAL_TYPES = {
    "vab_just_value": "Petition contesting the just (market) value of a residential parcel",
    "vab_classified_use": "Petition contesting classified-use or assessed value",
    "vab_exemption_denial": "Petition contesting an exemption or classification denial",
    "vab_portability": "Petition contesting a portability determination",
    "informal_characteristics_correction": "Request to the property appraiser to correct recorded characteristics",
}
SUPPORTED_APPEAL_TYPES = {"vab_just_value"}

PROCESSING = ("completed", "partial", "failed")
ARGUMENT = ("supports_reduction", "insufficient_evidence", "does_not_support", "contradicted", "not_analyzed")
READINESS = ("not_ready", "ready_for_human_review")


class SourceUnavailable(RuntimeError):
    pass


class InputError(ValueError):
    pass


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_obj(obj) -> str:
    return sha256_text(canonical(obj))


def ym_label(ym: float | int | None) -> str | None:
    if ym is None:
        return None
    ym = int(ym)
    return f"{ym // 12}-{ym % 12 + 1:02d}"


@dataclass
class Item:
    evidence_id: str
    kind: str
    title: str
    origin: str
    source: dict
    facts: dict
    verification: str
    used_for: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    county_facing: bool = True

    def as_dict(self) -> dict:
        return {"evidence_id": self.evidence_id, "kind": self.kind, "title": self.title, "origin": self.origin,
                "source": self.source, "facts": self.facts, "verification": self.verification,
                "used_for": self.used_for, "limitations": self.limitations, "county_facing": self.county_facing}
