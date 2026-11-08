# File integration

For Tarang. This is what File receives from Evidence and how to use it without rebuilding anything.

## Where it is

Every Evidence run writes `file-handoff/` next to its `result.json`, and the agent publishes `evidence.json` and
`packet.pdf` on Naïve with the title `Evidence <cycle_id> v<version> <file>`. The card's JSON block carries the file ids,
`packet_sha256` and `evidence_status`.

```
file-handoff/
  evidence.json          the `evidence` object for case-handoff.json
  evidence-packet.pdf    the reviewed packet (same bytes as packet.pdf)
  verification-<n>.json  one record per Find verification Evidence could establish
  evidence-result.json   compact result for reference
```

All artifact paths are relative to `file-handoff/`. Copy the folder's contents into the case handoff directory and set
`envelope["evidence"]` to the contents of `evidence.json`; the paths and hashes then match what `local_artifact` checks.

## The evidence object

```json
{
  "case_id": "FL-13-2026-30933354000",
  "tax_year": 2026,
  "status": "complete",
  "artifact": {"path": "evidence-packet.pdf", "sha256": "…"},
  "verifications": [
    {"check": "<exact Find needs_verification string>", "status": "verified", "by": "Evidence rules configuration",
     "method": "configured_official_source", "artifact": {"path": "verification-2.json", "sha256": "…"}},
    {"check": "<exact string>", "status": "unverified", "reason": "needs the parcel's billed millage"}
  ],
  "unverified_checks": ["…"],
  "not_complete_because": [],
  "source": {"schema": "claimos.evidence.result/1", "run_id": "…", "cycle_id": "…", "packet_version": 1, "packet_sha256": "…"},
  "readiness": {"…": "…"}
}
```

- `case_id` is Find's `candidate.case_id`, and `tax_year` matches the candidate.
- `status` is `complete` only when the packet passed validation, supports a reduction, has every required item, and a
  person approved this exact packet for `file_handoff`. Otherwise it is `incomplete` (with reasons) or
  `synthetic_fixture`, which must never be filed.
- `verifications` has one entry per string in `candidate.needs_verification`, in the same order and with the identical
  text. Evidence marks a check `verified` only with an artifact: the petition deadline from a configured official source,
  and the county self-check or thin-sales concern when its own sales comparison is reliable. Millage, condition, record
  card, owner changes and the property's own contradicting sale stay `unverified` until a person records them; File's
  rule that each check needs exactly one verified entry keeps those cases blocked, as intended.

## Checking before use

`claimevidence check-handoff result.json` exits 0 only when the result is usable: completed run, validated packet, human
review of this exact packet with approval for `file_handoff`, valid authorization, not superseded. It always reports
`filing_approval_still_required: true`; Evidence approval is not a filing approval.

## Things File should know

- DOR revised DR-486 to R. 11/26 (effective 2026-11-02). Confirm the template File fetches is that revision.
- DR-486POA (R. 12/20) needs the taxpayer's signature, two witnesses and a notary. A compensated authorization without
  them should not reach File; Sign up needs to collect all three.
- Lee: the exchange goes to the property appraiser at vabmail@leepa.org; an Axia upload to the clerk is not the exchange.
  Hendry opted out of remote hearings for 2026.
- The petition is never held back for the packet. The delivery plan lists `petition_dr486` as File's item with its own
  deadline; the evidence exchange is due 15 days before the hearing and is a separate delivery.
- Bay's 2026 petition deadline was September 8, 2026 (Bay Clerk). Bay remains blocked in File until a Bay adapter exists.
- The packet's identification page shows "Petition number: Not yet assigned" until File records the clerk's number;
  pass it back as `submission.petition_number` so a remote-hearing upload carries it.
