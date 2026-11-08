"""Florida Department of Revenue data portal: every county's roll (NAL) and sales file (SDF),
published in one statewide format. Discovery goes through the portal's SharePoint REST API, so new
files (preliminary rolls in summer, final rolls in fall) are picked up without code changes."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

import pandas as pd

from ....engine.ingest import HttpCache, safe_extract

HOST = "https://floridarevenue.com"
PORTAL = HOST + "/property/dataportal"
ROOT = "/property/dataportal/Documents/PTO Data Portal/Tax Roll Data Files"
FILE_RE = re.compile(r"^(?P<county>.+?) (?P<no>\d{2}) (?P<stage>Final|Preliminary) (?P<kind>NAL|SDF|NAP) (?P<year>\d{4})\.zip$", re.I)

NAL_NUM = ["JV", "JV_CHNG", "AV_SD", "AV_NSD", "TV_SD", "TV_NSD", "JV_HMSTD", "AV_HMSTD",
           "JV_NON_HMSTD_RESD", "AV_NON_HMSTD_RESD", "LND_VAL", "LND_SQFOOT", "EFF_YR_BLT", "ACT_YR_BLT",
           "TOT_LVG_AREA", "NO_BULDNG", "NO_RES_UNTS", "SPEC_FEAT_VAL", "ASMNT_YR"]
NAL_STR = ["CO_NO", "PARCEL_ID", "DOR_UC", "JV_CHNG_CD", "MKT_AR", "NBRHD_CD", "TAX_AUTH_CD", "ALT_KEY",
           "PHY_ADDR1", "PHY_ADDR2", "PHY_CITY", "PHY_ZIPCD", "S_LEGAL", "TWN", "RNG", "SEC", "CENSUS_BK",
           "OWN_NAME", "OWN_ADDR1", "OWN_ADDR2", "OWN_CITY", "OWN_STATE", "OWN_ZIPCD", "OWN_STATE_DOM"]
PARSE_VERSION = 3   # bump when the column lists change so cached parquet is rebuilt
SDF_NUM = ["SALE_YR", "SALE_MO", "SALE_PRC"]
SDF_STR = ["PARCEL_ID", "QUAL_CD", "VI_CD", "MULTI_PAR_SAL", "SALE_ID_CD", "OR_BOOK", "OR_PAGE", "CLERK_NO"]


@dataclass(frozen=True)
class RollFile:
    county: str
    county_no: str
    stage: str      # "final" | "preliminary"
    kind: str       # "NAL" | "SDF" | "NAP"
    year: int
    url: str
    size: int
    modified: str


def _api(cache: HttpCache, path: str, what: str) -> list[dict]:
    fields = "Name,ServerRelativeUrl,ItemCount" if what == "Folders" else "Name,Length,TimeLastModified,ServerRelativeUrl"
    url = f"{PORTAL}/_api/web/GetFolderByServerRelativeUrl('{quote(path)}')/{what}?$select={fields}&$top=500"
    return cache.get_json(url, headers={"Accept": "application/json;odata=nometadata"}).get("value", [])


def list_roll_files(cache: HttpCache, kinds=("NAL", "SDF")) -> list[RollFile]:
    files: list[RollFile] = []
    for kind in kinds:
        for folder in _api(cache, f"{ROOT}/{kind}", "Folders"):
            for f in _api(cache, folder["ServerRelativeUrl"], "Files"):
                m = FILE_RE.match(f["Name"])
                if not m:
                    continue
                files.append(RollFile(
                    county=m["county"].strip(), county_no=m["no"], stage=m["stage"].lower(), kind=m["kind"].upper(),
                    year=int(m["year"]), url=HOST + quote(f["ServerRelativeUrl"]),
                    size=int(f.get("Length") or 0), modified=f.get("TimeLastModified", "")))
    return files


def latest_pairs(files: list[RollFile], year: int | None = None) -> dict[str, dict[str, RollFile]]:
    """Newest roll per county that has both a NAL and an SDF for the same year and stage.
    A final roll beats a preliminary one of the same year."""
    rank = {"final": 2, "preliminary": 1}
    by = {}
    for f in files:
        if year and f.year != year:
            continue
        by.setdefault((f.county_no, f.year, f.stage), {})[f.kind] = f
    best: dict[str, dict[str, RollFile]] = {}
    for (cno, yr, stage), kinds in by.items():
        if "NAL" not in kinds or "SDF" not in kinds:
            continue
        cur = best.get(cno)
        key = (yr, rank[stage])
        if cur is None or key > (cur["NAL"].year, rank[cur["NAL"].stage]):
            best[cno] = kinds
    return best


# Text columns dominate a county roll: 24 of the NAL's 43 columns are strings, and as Python
# objects they cost ~28 MB each on a big county (Lee: 946 MB for the frame). Arrow-backed strings
# store the same data as contiguous buffers and cut that by roughly 3x, which is the difference
# between fitting in the agent sandbox and being OOM-killed. Falls back silently if pyarrow is absent.
try:
    import pyarrow  # noqa: F401
    STR_DTYPE = "string[pyarrow]"
except ImportError:  # pragma: no cover
    STR_DTYPE = "string"


def _shrink(df: pd.DataFrame, num: list[str], strs: list[str]) -> pd.DataFrame:
    """Numeric columns to plain float64 (nullable dtypes turn NaN comparisons into NA, not False);
    text columns to Arrow-backed strings. Applied on both the parse and the parquet-cache paths so
    a warm run is no heavier than a cold one."""
    for c in num:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").astype("float64")
    for c in strs:
        if c in df.columns:
            df[c] = df[c].astype(STR_DTYPE)
        else:
            df[c] = pd.Series(pd.NA, index=df.index, dtype=STR_DTYPE)
    return df


def _read_csv(path: Path, num: list[str], strs: list[str]) -> pd.DataFrame:
    wanted = set(num) | set(strs)
    df = pd.read_csv(path, usecols=lambda c: c in wanted, dtype=STR_DTYPE, low_memory=False)
    return _shrink(df, num, strs)


def load_pair(cache: HttpCache, pair: dict[str, RollFile], work: Path) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Download (if changed), extract, parse and cache as parquet keyed by file hash."""
    out = {}
    meta = {}
    for kind, num, strs in (("NAL", NAL_NUM, NAL_STR), ("SDF", SDF_NUM, SDF_STR)):
        rf = pair[kind]
        got = cache.fetch(rf.url, name=f"{rf.county_no}_{rf.kind}_{rf.year}_{rf.stage}.zip")
        pq = work / f"{rf.county_no}_{kind}_{rf.year}_{rf.stage}_{got.meta['sha256'][:12]}_v{PARSE_VERSION}.parquet"
        if pq.exists():
            df = pd.read_parquet(pq)
        else:
            tmp = work / f"x_{rf.county_no}_{kind}"
            csvs = safe_extract(got.path, tmp)
            if not csvs:
                raise ValueError(f"no CSV inside {rf.url}")
            df = _read_csv(csvs[0], num, strs)
            df.to_parquet(pq, index=False)
            for p in csvs:
                p.unlink(missing_ok=True)
        df = _shrink(df, num, strs)
        out[kind] = df
        meta[kind] = {"url": rf.url, "sha256": got.meta["sha256"], "changed": got.changed, "modified": rf.modified}
    return out["NAL"], out["SDF"], meta
