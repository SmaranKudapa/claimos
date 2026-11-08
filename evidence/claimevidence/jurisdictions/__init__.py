from __future__ import annotations

from . import florida

REGISTRY = {florida.STATE: florida}


def resolve(state: str | None) -> dict:
    mod = REGISTRY.get((state or "").strip().upper())
    if mod is None:
        return {"status": "unsupported", "state": state, "module": None,
                "reason": f"no researched rule set for {state!r}; Evidence does not apply another state's deadlines, valuation rules, forms or terms"}
    return {"status": "supported", "state": mod.STATE, "module": mod, "ruleset": mod.RULESET}
