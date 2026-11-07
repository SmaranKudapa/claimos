"""Thin Python client for the Naive (Vetta) Managed Agents API — only the routes Find uses.

Routes and shapes follow @usenaive-sdk/managed-agents 0.12 (the typed TypeScript client):
  GET  /v1/data/tools?query=&domain=&limit=     data catalogue search
  GET  /v1/data/tools/{id}                      a tool's input schema + price
  POST /v1/data/runs {tool_id, path, query, body}
  POST /v1/boards/{agt_|brd_ id}/cards {title, body, status, assignee, key}   key = idempotent create
  POST /v1/deployments {agent_id, cron, timezone, input_template, budget_micro_usd}
Auth: Authorization: Bearer <NAIVE_API_KEY>; every write carries an idempotency-key.

dry_run=True records each request to an outbox file instead of sending it, so the whole pipeline
can be rehearsed without a key and the exact calls inspected.
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

import requests


class NaiveError(RuntimeError):
    pass


class NaiveClient:
    def __init__(self, api_key: str | None, base_url: str = "https://api.vetta.sh", dry_run: bool = False,
                 outbox: Path | None = None, session: requests.Session | None = None):
        self.api_key = api_key
        self.base = base_url.rstrip("/")
        self.dry_run = dry_run or not api_key
        self.outbox = Path(outbox) if outbox else None
        self.s = session or requests.Session()

    @property
    def live(self) -> bool:
        return not self.dry_run

    def _call(self, method: str, path: str, query: dict | None = None, body: dict | None = None,
              idem: str | None = None) -> dict:
        if self.dry_run:
            if self.outbox:
                self.outbox.parent.mkdir(parents=True, exist_ok=True)
                with open(self.outbox, "a") as fh:
                    fh.write(json.dumps({"method": method, "path": path, "query": query, "body": body,
                                         "idempotency_key": idem}) + "\n")
            return {"dry_run": True, "id": f"dry_{uuid.uuid4().hex[:10]}"}
        headers = {"authorization": f"Bearer {self.api_key}", "accept": "application/json"}
        if method in ("POST", "PATCH", "PUT", "DELETE"):
            headers["idempotency-key"] = idem or str(uuid.uuid4())
        for attempt in range(4):
            r = self.s.request(method, self.base + path, params=query, json=body, headers=headers, timeout=120)
            if r.status_code in (429, 502, 503, 504):
                time.sleep(min(30, 2 ** attempt + float(r.headers.get("retry-after", 0) or 0)))
                continue
            if r.status_code >= 400:
                raise NaiveError(f"{method} {path} -> {r.status_code}: {r.text[:300]}")
            return r.json() if r.content else {}
        raise NaiveError(f"{method} {path}: gave up after retries")

    # data catalogue
    def search_data_tools(self, query: str, domain: str | None = "real_estate", limit: int = 20) -> list[dict]:
        q = {"query": query, "limit": limit}
        if domain:
            q["domain"] = domain
        return self._call("GET", "/v1/data/tools", query=q).get("data", [])

    def data_tool(self, tool_id: str) -> dict:
        return self._call("GET", f"/v1/data/tools/{tool_id}")

    def run_data_tool(self, tool_id: str, path: dict | None = None, query: dict | None = None,
                      body: dict | None = None, idem: str | None = None) -> dict:
        req = {"tool_id": tool_id}
        if path:
            req["path"] = path
        if query:
            req["query"] = query
        if body:
            req["body"] = body
        return self._call("POST", "/v1/data/runs", body=req, idem=idem)

    # board
    def create_card(self, board_ref: str, title: str, body: str, key: str, assignee: str | None = None,
                    status: str = "todo") -> dict:
        card = {"title": title[:200], "body": body, "status": status, "key": key[:128]}
        if assignee:
            card["assignee"] = assignee
        return self._call("POST", f"/v1/boards/{board_ref}/cards", body=card, idem=f"card-{key}"[:128])

    # schedules
    def create_deployment(self, agent_id: str, cron: str, input_template: str, budget_usd: float,
                          timezone: str = "America/New_York") -> dict:
        return self._call("POST", "/v1/deployments", body={
            "agent_id": agent_id, "cron": cron, "timezone": timezone, "input_template": input_template,
            "budget_micro_usd": int(budget_usd * 1_000_000)})
