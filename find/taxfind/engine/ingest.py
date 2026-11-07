"""Data ingestion: cached, conditional downloads and safe archive handling.

A manifest beside the cache remembers each URL's ETag / Last-Modified / size so a scheduled run
only re-downloads (and re-screens) what actually changed.
"""
from __future__ import annotations

import hashlib
import json
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path

import requests

UA = "taxappeal-find/0.1 (+public records ingestion)"


@dataclass
class Fetched:
    path: Path
    changed: bool
    meta: dict


class HttpCache:
    def __init__(self, root: Path, session: requests.Session | None = None):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.root / "manifest.json"
        self.session = session or requests.Session()
        self.session.headers.setdefault("User-Agent", UA)
        try:
            self.manifest = json.loads(self.manifest_path.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            self.manifest = {}

    def _save(self) -> None:
        tmp = self.manifest_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.manifest, indent=1, sort_keys=True))
        tmp.replace(self.manifest_path)

    def path_for(self, url: str, name: str | None = None) -> Path:
        h = hashlib.sha1(url.encode()).hexdigest()[:12]
        safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in (name or url.rsplit("/", 1)[-1]))
        return self.root / f"{h}_{safe}"

    def get_json(self, url: str, headers: dict | None = None, timeout: int = 60) -> dict:
        r = self._request("GET", url, headers=headers, timeout=timeout)
        r.raise_for_status()
        return r.json()

    def fetch(self, url: str, name: str | None = None, timeout: int = 600) -> Fetched:
        dest = self.path_for(url, name)
        prev = self.manifest.get(url, {})
        headers = {}
        if dest.exists() and prev:
            if prev.get("etag"):
                headers["If-None-Match"] = prev["etag"]
            if prev.get("last_modified"):
                headers["If-Modified-Since"] = prev["last_modified"]
        r = self._request("GET", url, headers=headers, timeout=timeout, stream=True)
        if r.status_code == 304 and dest.exists():
            return Fetched(dest, False, prev)
        r.raise_for_status()
        tmp = dest.with_suffix(dest.suffix + ".part")
        sha = hashlib.sha256()
        with open(tmp, "wb") as fh:
            for chunk in r.iter_content(1 << 20):
                fh.write(chunk)
                sha.update(chunk)
        digest = sha.hexdigest()
        changed = digest != prev.get("sha256")
        tmp.replace(dest)
        meta = {"etag": r.headers.get("ETag"), "last_modified": r.headers.get("Last-Modified"),
                "size": dest.stat().st_size, "sha256": digest, "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        self.manifest[url] = meta
        self._save()
        return Fetched(dest, changed, meta)

    def _request(self, method: str, url: str, retries: int = 3, **kw) -> requests.Response:
        last = None
        for attempt in range(retries):
            try:
                r = self.session.request(method, url, **kw)
                if r.status_code in (429, 500, 502, 503, 504):
                    last = requests.HTTPError(f"{r.status_code} from {url}")
                    time.sleep(2 ** attempt)
                    continue
                return r
            except requests.RequestException as e:  # network blip
                last = e
                time.sleep(2 ** attempt)
        raise last  # type: ignore[misc]


def safe_extract(zip_path: Path, out_dir: Path, suffixes: tuple[str, ...] = (".csv", ".txt")) -> list[Path]:
    """Extract only plain data files, refusing any member that would land outside out_dir."""
    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    extracted = []
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            if info.is_dir() or not info.filename.lower().endswith(suffixes):
                continue
            target = (out_dir / Path(info.filename).name).resolve()
            if out_dir not in target.parents:
                raise ValueError(f"unsafe path in archive: {info.filename}")
            with zf.open(info) as src, open(target, "wb") as dst:
                while True:
                    buf = src.read(1 << 20)
                    if not buf:
                        break
                    dst.write(buf)
            extracted.append(target)
    return extracted
