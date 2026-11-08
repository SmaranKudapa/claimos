from __future__ import annotations


def render_internal(base, col, a, val, items, matrix, rules, deadlines, intake, tasks, inp) -> str:
    ap = base["appeal"]
    L = [f"# Internal review record — {ap['cycle_id']}", "",
         "Not for submission. Contains operational notes, uncertainty, estimates and private references.", ""]
    L.append("## Intake checks")
    L.append("")
    L.append("| Check | Status | Detail | Blocks | Resolver |\n|---|---|---|---|---|")
    for c in intake["checks"]:
        L.append(f"| {c['id']} {c['check']} | {c['status']} | {c['detail']} | {c['blocks']} | {c['resolver'] or ''} |")
    L.append("")
    L.append("## Requirements")
    L.append("")
    L.append("| ID | Requirement | Required | Status | Resolver | Missing |\n|---|---|---|---|---|---|")
    for r in matrix:
        L.append(f"| {r['id']} | {r['requirement']} | {'yes' if r['required'] else 'no'} | {r['status']} | {r['resolver'] or ''} | {r['missing'] or ''} |")
    L.append("")
    if val and val.get("tax_estimate"):
        t = val["tax_estimate"]
        L.append("## Estimated tax effect (internal only, never a promise)")
        L.append("")
        L.append(f"About ${t['annual_savings']:,}/yr, range ${t['annual_savings_range'][0]:,}–${t['annual_savings_range'][1]:,}, on {t['rate_basis']} rates. {t['caveat']}")
        L.append("")
        L.append(f"Effects: {val['effects']}")
        L.append("")
    if val and val.get("versus_find"):
        L.append("## Versus Find")
        L.append("")
        L.append(f"{val['versus_find']}")
        L.append("")
    L.append("## Deadlines (kept separate)")
    L.append("")
    for k, d in (deadlines or {}).items():
        L.append(f"- **{k.replace('_', ' ')}:** {d.get('date') or 'not set'} ({d.get('status')}; verified={d.get('verified')}). Trigger: {d.get('trigger')}. {d.get('basis') or ''}")
    L.append("")
    L.append("## Homeowner requests (not sent)")
    L.append("")
    for t in tasks:
        L.append(f"- {t['task_id']} {t['title']} — blocking={t['blocking']}, delivery={t['delivery']}")
    L.append("")
    L.append("## Rules applied")
    L.append("")
    for r in rules:
        L.append(f"- [{r['id']}] ({r['status']}) {r['summary']} — {r['source']} {r.get('section') or ''} (checked {r.get('retrieved')}). Applied as: {r.get('applied_as')}")
    L.append("")
    auth = inp.get("authorization") or {}
    L.append("## Authorization reference")
    L.append("")
    L.append(f"status={auth.get('status')} instrument={auth.get('instrument')} document_ref={auth.get('document_ref')} signed_at={auth.get('signed_at')}")
    return "\n".join(L) + "\n"
