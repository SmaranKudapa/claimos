# Claim OS website

This source is based on the deployed `claimos-site` app. It preserves the homeowner email-link tracking flow and adds recorded workflow progress and county filing guidance.

## Workflow visibility

`/workflow` exposes aggregate Qualify, Evidence and File outcomes from the company board, with replay and fixture markers and a receipt count. It never publishes case IDs, owner emails, addresses, notes or document references. `/track` merges the same projection only into the cases authorized by the existing signed owner link.

`/api/workflow` refreshes the board projection at most once per minute per warm worker; the page polls every 30 seconds while visible. A private database snapshot survives cold starts and provider outages. A failed refresh returns the previous timestamped snapshot as stale. No agent, card, schedule or agent budget is modified. Existing site-sync behavior is independent and remains unchanged.

The server requires `CLAIMOS_WORKFLOW_READ_KEY`, scoped to `agents:read` only. No key belongs in client assets or source. Without the key, the website displays the saved snapshot and explicitly says automatic updates are unavailable.

Apply `db/migrations/002_workflow_snapshot.sql` to the `claimos-site` app database. The table uses row-level security and is read through the existing server-side database service connection. Do not add an anonymous read policy.

## File: where and how

`/filing` links the official Lee, Hendry and Bay county instructions and Florida petition forms, with destinations, submission methods, fee notes and deadline caveats. It explains the five separate responsibilities: route, preparation, authority/submission, receipt custody and notice-derived follow-up. It does not file, send messages, sign or pay. Bay's automated filing adapter remains disabled.

County sources were checked November 7, 2026. Case-specific deadlines and approvals must still come from the actual record. Petition filing and evidence exchange are separate.

## Verification

Run `npm run typecheck` and `npm test`. Tests cover replay separation, incomplete Evidence, receipt requirements, case identity conflicts, stage deduplication, public-data privacy, owner isolation and official filing links. Browser verification covers the workflow display, county selection and existing tracking entry point.
