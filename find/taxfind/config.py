"""Settings. Everything is overridable by environment variable so the same code runs on a laptop,
in CI, or inside a Naive agent sandbox on a cron deployment."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env(name: str, default: str | None = None) -> str | None:
    v = os.environ.get(name)
    return v if v not in (None, "") else default


def _float(name: str, default: float) -> float:
    return float(_env(name, str(default)))


def _int(name: str, default: int) -> int:
    return int(_env(name, str(default)))


@dataclass
class ScreenParams:
    """Detection rule for the property-tax desk. Defaults were tuned on Lee County's 2026 roll."""
    uni_threshold: float = 1.15        # value/sq ft at least 15% above similar nearby homes
    mkt_threshold: float = 1.10        # at least 10% above the county's normal value-to-price level
    min_peers: int = 8
    min_comps: int = 3
    size_band: float = 0.20            # |log(sqft ratio)| for neighbors
    comp_size_band: float = 0.25
    age_band: int = 10                 # effective-year window for neighbors
    land_band: float = 0.35            # |log(land value ratio)| for houses (keeps waterfront apart)
    min_savings_strong: float = 500.0
    outlier_uni: float = 1.75
    outlier_mkt: float = 1.90
    high_value: float = 2_000_000
    new_build_year_offset: int = 2     # built within 2 years of the roll year -> set aside
    millage: float = 0.015             # assumed all-in rate when no per-county rate is configured
    millage_school: float = 0.0055     # of which school levies (taxed on AV_SD); typical FL district 5-6 mills
    trim_iqr: float = 0.0              # >0 drops comparable sales outside that many IQRs of value/price (tested 1.5: no gain)
    own_sale_floor: float = 1.0        # own recent sale implies the value is fine -> review, not mail
    holdout_min_n: int = 30            # flagged homes that sold later, needed to judge a county
    holdout_min_lift: float = 1.25     # flagged must sell below county value 25%+ more often than others


@dataclass
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(_env("FIND_DATA_DIR", "./data")).resolve())
    screen: ScreenParams = field(default_factory=ScreenParams)

    # Second opinion from home-value estimates (Zillow / Redfin / Naive data catalogue)
    avm_providers: list[str] = field(default_factory=lambda: _env(
        "FIND_AVM_PROVIDERS", "naive,apify_zillow,apify_redfin").split(","))
    avm_budget_usd: float = field(default_factory=lambda: _float("FIND_AVM_BUDGET_USD", 5.0))
    avm_max_lookups: int = field(default_factory=lambda: _int("FIND_AVM_MAX_LOOKUPS", 300))
    avm_cache_days: int = field(default_factory=lambda: _int("FIND_AVM_CACHE_DAYS", 60))

    # Naive
    naive_api_key: str | None = field(default_factory=lambda: _env("NAIVE_API_KEY"))
    naive_base_url: str = field(default_factory=lambda: _env("NAIVE_API_BASE_URL", "https://api.vetta.sh"))
    naive_board: str | None = field(default_factory=lambda: _env("NAIVE_QUALIFY_BOARD"))
    naive_qualify_agent: str | None = field(default_factory=lambda: _env("NAIVE_QUALIFY_AGENT"))
    naive_real_estate_tool: str | None = field(default_factory=lambda: _env("NAIVE_REAL_ESTATE_TOOL"))

    # Apify
    apify_token: str | None = field(default_factory=lambda: _env("APIFY_TOKEN"))
    apify_zillow_actors: list[str] = field(default_factory=lambda: _env(
        "APIFY_ZILLOW_ACTORS", "maxcopell~zillow-detail-scraper,kawsar~affordable-zillow-details-scraper").split(","))
    apify_redfin_actor: str = field(default_factory=lambda: _env("APIFY_REDFIN_ACTOR", "tri_angle~redfin-detail"))

    handoff_max_cards: int = field(default_factory=lambda: _int("FIND_HANDOFF_MAX_CARDS", 200))
    handoff_include_closed: bool = field(default_factory=lambda: _env("FIND_HANDOFF_INCLUDE_CLOSED", "0") in ("1", "true", "yes"))
    dry_run: bool = field(default_factory=lambda: _env("FIND_DRY_RUN", "0") in ("1", "true", "yes"))

    @property
    def db_path(self) -> Path:
        return self.data_dir / "find.sqlite"

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    @property
    def out_dir(self) -> Path:
        return self.data_dir / "out"

    def ensure(self) -> "Settings":
        for p in (self.data_dir, self.cache_dir, self.out_dir):
            p.mkdir(parents=True, exist_ok=True)
        return self
