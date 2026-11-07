"""Detection rule for over-assessed homes. State-agnostic once a roll is in the common columns:

  PARCEL_ID, DOR_UC ('001' house / '004' condo), NBRHD_CD, JV, AV_NSD, JV_HMSTD, LND_VAL,
  TOT_LVG_AREA, EFF_YR_BLT, ACT_YR_BLT  +  sales: PARCEL_ID, SALE_YR, SALE_MO, SALE_PRC,
  QUAL_CD, VI_CD, MULTI_PAR_SAL

Two independent signals per home:
  1. neighbor_ratio: county value per sq ft vs. similar homes in the same appraisal neighborhood
  2. sales_ratio: county value vs. what comparable homes sold for (time-adjusted to the valuation
     date), relative to the county's own normal value-to-price level
Savings count only where a lower value would fall below the capped assessed value.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ...config import ScreenParams
from ...engine.normalize import norm_street_series

USES = {"001": "single_family", "004": "condo"}
DEFAULT_LEVEL = {"001": 0.84, "004": 0.80}   # fallback when a county has too few sales to measure
QUALIFIED = ("01", "02")


def _masked_median(mask: np.ndarray, vals: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    x = np.where(mask, vals[None, :], np.nan)
    with np.errstate(all="ignore"):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            return np.nanmedian(x, axis=1), mask.sum(axis=1)


def prepare(nal: pd.DataFrame, min_building: int = 9, max_group: int = 4000, min_geo: int = 40) -> pd.DataFrame:
    nal = nal.copy()
    # peer group: the appraisal neighborhood; where a county leaves it blank, its market area (coarser)
    nb = nal.NBRHD_CD.astype("string").str.strip().replace("", pd.NA)
    nal["peer_basis"] = "neighborhood"
    if "MKT_AR" in nal.columns:
        mk = nal.MKT_AR.astype("string").str.strip().replace("", pd.NA)
        use_mk = nb.isna() & mk.notna()
        nb = nb.where(~use_mk, "MKT:" + mk)
        nal.loc[use_mk, "peer_basis"] = "market_area"
    nal["NBRHD_ORIG"] = nal.NBRHD_CD
    nal["NBRHD_CD"] = nb
    r = nal[nal.DOR_UC.isin(list(USES)) & (nal.TOT_LVG_AREA > 300) & (nal.JV > 20000) & nal.NBRHD_CD.notna()].copy()
    r["sqft"] = r.TOT_LVG_AREA.astype(float)
    r["eff"] = r.EFF_YR_BLT.where(r.EFF_YR_BLT > 0, r.ACT_YR_BLT).astype(float)
    r["land"] = r.LND_VAL.fillna(0).astype(float)
    r["homestead"] = r.JV_HMSTD.fillna(0) > 0
    r["ppsf"] = r.JV / r.sqft
    # condos are compared within their own building when it is big enough: a county that puts a
    # whole beach town in one neighborhood would otherwise compare Gulf-front towers with back-bay units
    condo = r.DOR_UC == "004"
    if condo.any():
        streets = r.loc[condo, "PHY_ADDR1"].astype("string").fillna("")
        uniq = pd.Series(streets.unique(), dtype="object")
        smap = dict(zip(uniq, norm_street_series(uniq)))
        zips = r.loc[condo, "PHY_ZIPCD"].astype("string").fillna("").str.replace(r"\D", "", regex=True).str[:5] \
            if "PHY_ZIPCD" in r.columns else ""
        bkey = r.loc[condo, "NBRHD_CD"].astype(str) + "|B:" + streets.map(smap) + "|" + zips
        size = bkey.map(bkey.value_counts())
        big = (size >= min_building) & (streets.map(smap) != "")
        r.loc[big[big].index, "NBRHD_CD"] = bkey[big]
        r.loc[big[big].index, "peer_basis"] = "building"
    # a "neighborhood" covering most of a county is no neighborhood: split it by survey section
    # (one square mile), or by township (6 x 6 miles) where a section has too few homes
    if {"TWN", "RNG", "SEC"} <= set(r.columns):
        gsize = r.groupby(["DOR_UC", "NBRHD_CD"]).PARCEL_ID.transform("size")
        over = (gsize > max_group) & (r.peer_basis != "building")
        if over.any():
            tw = r.TWN.astype("string").fillna("").str.strip() + r.RNG.astype("string").fillna("").str.strip()
            sec = tw + "-" + r.SEC.astype("string").fillna("").str.strip()
            base = r.DOR_UC.astype(str) + "|" + r.NBRHD_CD.astype(str)
            n_sec = (base + "|" + sec).map((base + "|" + sec)[over].value_counts())
            n_tw = (base + "|" + tw).map((base + "|" + tw)[over].value_counts())
            use_sec = over & (tw != "") & (n_sec >= min_geo)
            use_tw = over & ~use_sec & (tw != "") & (n_tw >= min_geo)
            r.loc[use_sec, "NBRHD_CD"] = r.loc[use_sec, "NBRHD_CD"].astype(str) + "|S:" + sec[use_sec]
            r.loc[use_sec, "peer_basis"] = "section"
            r.loc[use_tw, "NBRHD_CD"] = r.loc[use_tw, "NBRHD_CD"].astype(str) + "|T:" + tw[use_tw]
            r.loc[use_tw, "peer_basis"] = "township"
    return r.reset_index(drop=True)


def qualified_sales(sdf: pd.DataFrame, homes: pd.DataFrame) -> pd.DataFrame:
    q = sdf[sdf.QUAL_CD.isin(QUALIFIED) & (sdf.VI_CD == "I") & sdf.MULTI_PAR_SAL.isna() & (sdf.SALE_PRC > 20000)]
    q = q[["PARCEL_ID", "SALE_YR", "SALE_MO", "SALE_PRC"] + [c for c in ("SALE_ID_CD", "CLERK_NO") if c in q.columns]]
    q = q.merge(homes[["PARCEL_ID", "DOR_UC", "NBRHD_CD", "sqft", "eff", "land", "JV", "PHY_ADDR1"]], on="PARCEL_ID", how="inner")
    q = q.dropna(subset=["SALE_YR", "SALE_MO"])
    q["ppsf"] = q.SALE_PRC / q.sqft
    q["ym"] = (q.SALE_YR * 12 + q.SALE_MO - 1).astype(int)
    return q


def time_index(q: pd.DataFrame, valuation_ym: float, min_month: int = 40) -> tuple[dict[str, dict[int, float]], dict]:
    """Per use: factor that moves a sale's price to the valuation date (Jan 1 of the roll year).
    Monthly medians where a month has enough sales, else quarterly; the index is interpolated
    between points (never a 1.0 gap among adjusted months) and anchored at the valuation date.
    When the market is too thin to measure near the valuation date, no adjustment is made."""
    idx: dict[str, dict[int, float]] = {}
    how: dict[str, str] = {}
    for uc, g in q.groupby("DOR_UC"):
        months = np.arange(int(g.ym.min()), int(g.ym.max()) + 1)
        pts = None
        for unit, key in (("monthly", g.ym), ("quarterly", g.ym // 3)):
            counts = g.groupby(key).size()
            med = g.groupby(key).ppsf.median()[counts >= min_month].sort_index()
            if len(med) >= 4:
                x = med.index.to_numpy(float) * (1 if unit == "monthly" else 3) + (0 if unit == "monthly" else 1)
                y = med.rolling(3, center=True, min_periods=1).median().to_numpy(float)
                pts = (x, y, unit)
                break
        if pts is None or not (pts[0].min() - 3 <= valuation_ym <= pts[0].max() + 3):
            idx[uc], how[uc] = {int(m): 1.0 for m in months}, "none (too few sales near the valuation date)"
            continue
        x, y, unit = pts
        anchor = float(np.interp(valuation_ym, x, y))
        idx[uc] = {int(m): anchor / float(np.interp(m, x, y)) for m in months}
        how[uc] = f"{unit}, {len(x)} points"
    return idx, how


def screen(nal: pd.DataFrame, sdf: pd.DataFrame, roll_year: int, p: ScreenParams | None = None,
           millage: float | None = None) -> tuple[pd.DataFrame, dict]:
    p = p or ScreenParams()
    millage = millage if millage is not None else p.millage
    r = prepare(nal, min_building=p.min_peers + 1)
    r["level_factor_now"] = np.nan
    q = qualified_sales(sdf, r)
    vym = roll_year * 12            # Jan of roll year
    idx, time_how = time_index(q, vym - 0.5)      # between Dec and Jan
    q["tadj"] = [idx.get(u, {}).get(ym, 1.0) for u, ym in zip(q.DOR_UC, q.ym)]
    latest_factor = {u: (d[max(d)] if d else 1.0) for u, d in idx.items()}   # moves a value from "now" back to Jan 1
    q["ppsf_adj"] = q.ppsf * q.tadj
    comps_all = q[q.ym < vym]       # sales before the valuation date only
    # drop outlier sales the way assessment ratio studies do (IAAO: 1.5 x IQR fences on value/price):
    # a flood-damaged house sold as-is, or a sale with the price mis-keyed, is not a comparable
    trimmed = 0
    if p.trim_iqr and len(comps_all):
        ratio = comps_all.JV / (comps_all.SALE_PRC * comps_all.tadj)
        keep = pd.Series(True, index=comps_all.index)
        for uc in comps_all.DOR_UC.unique():
            m = comps_all.DOR_UC == uc
            if m.sum() < 30:
                continue
            q1, q3 = ratio[m].quantile([0.25, 0.75])
            iqr = q3 - q1
            keep &= ~m | ratio.between(q1 - p.trim_iqr * iqr, q3 + p.trim_iqr * iqr)
        trimmed = int((~keep).sum())
        comps_all = comps_all[keep]

    level, level_src = {}, {}
    for uc in USES:
        g = comps_all[comps_all.DOR_UC == uc]
        if len(g) >= 30:
            level[uc] = float((g.JV / (g.SALE_PRC * g.tadj)).median())
            level_src[uc] = f"measured on {len(g)} sales"
        else:
            level[uc] = DEFAULT_LEVEL[uc]
            level_src[uc] = "statewide default (too few local sales)"

    comps_by = {k: g.reset_index(drop=True) for k, g in comps_all.groupby(["DOR_UC", "NBRHD_CD"])}
    parts = []
    for key, g in r.groupby(["DOR_UC", "NBRHD_CD"], sort=False):
        # sorted by size, the homes within the size band of a chunk are one contiguous slice
        g = g.sort_values("sqft", kind="stable").reset_index(drop=True)
        n = len(g)
        lsq, eff, pp = np.log(g.sqft.to_numpy(float)), g.eff.to_numpy(float), g.ppsf.to_numpy(float)
        lland = np.log(np.maximum(g.land.to_numpy(float), 1))
        pid = g.PARCEL_ID.to_numpy(object)
        condo = key[0] == "004"
        c = comps_by.get(key)
        if c is not None and len(c):
            c = c.sort_values("sqft", kind="stable").reset_index(drop=True)
            clsq = np.log(c.sqft.to_numpy(float))
            cland = np.log(np.maximum(c.land.to_numpy(float), 1))
            cpid, cpp = c.PARCEL_ID.to_numpy(object), c.ppsf_adj.to_numpy(float)
        peer_med = np.full(n, np.nan); peer_n = np.zeros(n, int)
        comp_med = np.full(n, np.nan); comp_n = np.zeros(n, int)
        step = 500
        for a in range(0, n, step):
            b = min(a + step, n)
            lo = int(np.searchsorted(lsq, lsq[a] - p.size_band, "left"))
            hi = int(np.searchsorted(lsq, lsq[b - 1] + p.size_band, "right"))
            ds = np.abs(lsq[a:b, None] - lsq[None, lo:hi]) <= p.size_band
            if not condo:
                ds &= np.abs(lland[a:b, None] - lland[None, lo:hi]) <= p.land_band
            ds[np.arange(b - a), np.arange(a - lo, b - lo)] = False
            de = np.abs(eff[a:b, None] - eff[None, lo:hi]) <= p.age_band
            med, cnt = _masked_median(ds & de, pp[lo:hi])
            need = cnt < p.min_peers
            if need.any():
                med2, cnt2 = _masked_median(ds, pp[lo:hi])
                med, cnt = np.where(need, med2, med), np.where(need, cnt2, cnt)
            peer_med[a:b] = np.where(cnt >= p.min_peers, med, np.nan); peer_n[a:b] = cnt
            if c is not None and len(c):
                clo = int(np.searchsorted(clsq, lsq[a] - p.comp_size_band, "left"))
                chi = int(np.searchsorted(clsq, lsq[b - 1] + p.comp_size_band, "right"))
                if chi > clo:
                    mc = np.abs(lsq[a:b, None] - clsq[None, clo:chi]) <= p.comp_size_band
                    mc &= pid[a:b, None] != cpid[None, clo:chi]
                    if not condo:
                        mc &= np.abs(lland[a:b, None] - cland[None, clo:chi]) <= p.land_band
                    medc, nc = _masked_median(mc, cpp[clo:chi])
                    comp_med[a:b] = np.where(nc >= p.min_comps, medc, np.nan); comp_n[a:b] = nc
        g["peer_ppsf"], g["peer_n"], g["comp_ppsf"], g["comp_n"] = peer_med, peer_n, comp_med, comp_n
        parts.append(g)
    r = pd.concat(parts, ignore_index=True) if parts else r.assign(peer_ppsf=np.nan, peer_n=0, comp_ppsf=np.nan, comp_n=0)

    r["level"] = r.DOR_UC.map(level)
    r["neighbor_ratio"] = r.ppsf / r.peer_ppsf
    r["mkt_est"] = r.sqft * r.comp_ppsf
    r["sales_ratio"] = r.JV / (r.mkt_est * r.level)

    own = comps_all.sort_values("ym").groupby("PARCEL_ID").tail(1).set_index("PARCEL_ID")
    r["own_sale_price"] = r.PARCEL_ID.map(own.SALE_PRC)
    r["own_sale_ym"] = r.PARCEL_ID.map(own.ym)
    r["own_sale_ratio"] = r.JV / (r.PARCEL_ID.map(own.SALE_PRC * own.tadj) * r.level)

    both = ((r.neighbor_ratio >= p.uni_threshold) & (r.sales_ratio >= p.mkt_threshold)).fillna(False).astype(bool)
    target = np.fmax(r.peer_ppsf * r.sqft, r.level * r.mkt_est)
    r["defensible_value"] = target.where(target < r.JV)
    # Florida taxes school levies on AV_SD (no 10% non-homestead cap) and everything else on AV_NSD;
    # a cut only saves where the new value falls below the assessed value, and never more than the
    # taxable value left after exemptions (a fully exempt home saves nothing)
    def _cut(av_col, tv_col):
        base = r.AV_NSD.fillna(r.JV) if "AV_NSD" in r.columns else r.JV
        av = r[av_col].fillna(base) if av_col in r.columns else base
        cut = (av - np.minimum(av, r.defensible_value)).fillna(0).clip(lower=0)
        tv = r[tv_col] if tv_col in r.columns else (r["TV_NSD"] if "TV_NSD" in r.columns else None)
        if tv is not None:
            cut = np.minimum(cut, tv.fillna(av).clip(lower=0))
        return cut
    m_school = p.millage_school if millage is None or millage == p.millage else millage * p.millage_school / p.millage
    m_other = (millage if millage is not None else p.millage) - m_school
    r["taxable_cut_school"] = _cut("AV_SD", "TV_SD")
    r["taxable_cut"] = _cut("AV_NSD", "TV_NSD")
    r["value_cut"] = (r.JV - r.defensible_value).fillna(0).clip(lower=0)
    r["est_savings"] = r.taxable_cut_school * m_school + r.taxable_cut * m_other
    r["millage"] = m_school + m_other

    r["tier"] = "none"
    r.loc[both & (r.est_savings > 0), "tier"] = "possible"
    r.loc[both & (r.est_savings >= p.min_savings_strong), "tier"] = "strong"
    r.loc[both & (r.est_savings == 0), "tier"] = "cap_absorbs"
    outlier = ((r.neighbor_ratio > p.outlier_uni) | (r.sales_ratio > p.outlier_mkt) | (r.JV > p.high_value)).fillna(False).astype(bool)
    r.loc[both & (r.est_savings > 0) & outlier, "tier"] = "review"
    r.loc[both & (r.ACT_YR_BLT >= roll_year - p.new_build_year_offset), "tier"] = "new_build"
    # the home's own arm's-length sale beats any comparison: sold at or above what the value implies -> a person looks
    contra = (r.tier.isin(["strong", "possible"]) & (r.own_sale_ratio < p.own_sale_floor)).fillna(False).astype(bool)
    r["own_sale_contradicts"] = contra
    r.loc[contra, "tier"] = "review"

    # self-check on sales the screen never saw (after the valuation date): were flagged homes more
    # often sold for less than the county's value than everything else? Measured before those
    # sales are used below, so the check is not graded on its own answers.
    hold = q[q.ym >= vym].sort_values("ym").groupby("PARCEL_ID").tail(1)[["PARCEL_ID", "SALE_PRC", "tadj", "ym"]]
    h = r[["PARCEL_ID", "JV", "tier"]].merge(hold, on="PARCEL_ID")
    fl, nf = h[h.tier.isin(["strong", "possible"])], h[h.tier == "none"]
    f_over = float((fl.JV > fl.SALE_PRC).mean()) if len(fl) else None
    n_over = float((nf.JV > nf.SALE_PRC).mean()) if len(nf) else None
    lift = (f_over / n_over) if (f_over is not None and n_over) else None
    if len(fl) < p.holdout_min_n or lift is None:
        check = "untested"
    elif lift >= p.holdout_min_lift:
        check = "validated"
    else:
        check = "weak"
    holdout = {"flagged_sold": int(len(fl)), "flagged_sold_below_value": f_over, "others_sold": int(len(nf)),
               "others_sold_below_value": n_over, "lift": lift, "status": check}

    # now use them: a later arm's-length sale at a price that supports the value beats the comparison
    later = hold.set_index("PARCEL_ID")
    r["later_sale_price"] = r.PARCEL_ID.map(later.SALE_PRC)
    r["later_sale_ym"] = r.PARCEL_ID.map(later.ym)
    r["later_sale_ratio"] = r.JV / (r.PARCEL_ID.map(later.SALE_PRC * later.tadj) * r.level)
    contra2 = (r.tier.isin(["strong", "possible"]) & (r.later_sale_ratio < p.own_sale_floor)).fillna(False).astype(bool)
    r["own_sale_contradicts"] = r.own_sale_contradicts | contra2
    r.loc[contra2, "tier"] = "review"
    # any deed after Jan 1 (arm's length or not): the owner of record may have changed
    deeds = sdf.dropna(subset=["SALE_YR", "SALE_MO"])
    deeds = deeds[(deeds.SALE_YR * 12 + deeds.SALE_MO - 1) >= vym]
    last = deeds.assign(ym=(deeds.SALE_YR * 12 + deeds.SALE_MO - 1)).sort_values("ym").groupby("PARCEL_ID").ym.last()
    r["deed_since_roll_ym"] = r.PARCEL_ID.map(last)

    resid = int(nal.DOR_UC.isin(list(USES)).sum())
    stats = {
        "homes": int(len(r)),
        "house_condo_parcels": resid,
        "coverage": round(len(r) / resid, 4) if resid else 0.0,
        "peer_basis": {k: int(v) for k, v in r.peer_basis.value_counts().items()},
        "scored": int((r.peer_ppsf.notna() & r.comp_ppsf.notna()).sum()),
        "qualified_sales_before_valuation": int(len(comps_all)),
        "level": level, "level_source": level_src,
        "tiers": {k: int(v) for k, v in r.tier.value_counts().items()},
        "strong_savings_total": float(r.loc[r.tier == "strong", "est_savings"].sum()),
        "millage": millage,
        "own_sale_demoted": int(contra.sum()),
        "outlier_sales_dropped": trimmed,
        "later_sale_demoted": int(contra2.sum()),
        "time_adjustment": time_how,
        "level_factor_now": latest_factor,
        "holdout": holdout,
    }
    r["level_factor_now"] = r.DOR_UC.map(latest_factor)
    return r, {"stats": stats, "comps": comps_all}


def _nearest(target_sqft, target_land, target_pid, pool, band, land_band, condo, k):
    """Indices into pool of up to k nearest-in-size homes per target row (vectorized per group)."""
    lsq = np.log(pool.sqft.to_numpy(float))
    d = np.abs(np.log(target_sqft)[:, None] - lsq[None, :])
    m = (d <= band) & (target_pid[:, None] != pool.PARCEL_ID.to_numpy(object)[None, :])
    if not condo:
        pl = np.log(np.maximum(pool.land.to_numpy(float), 1))
        m &= np.abs(np.log(np.maximum(target_land, 1))[:, None] - pl[None, :]) <= land_band
    d = np.where(m, d, np.inf)
    kk = min(k, d.shape[1])
    idx = np.argpartition(d, kk - 1, axis=1)[:, :kk] if kk else np.zeros((len(d), 0), int)
    out = []
    for i in range(len(d)):
        row = idx[i][np.isfinite(d[i, idx[i]])]
        out.append(row[np.argsort(d[i, row])])
    return out


def evidence(r: pd.DataFrame, comps: pd.DataFrame, rows: pd.DataFrame, p: ScreenParams | None = None,
             k: int = 8) -> dict[str, dict]:
    """Neighbor and sale lists for the flagged rows only (the Evidence desk builds on these)."""
    p = p or ScreenParams()

    def s(v):
        return "" if v is None or (not isinstance(v, str) and pd.isna(v)) else str(v).strip()

    out: dict[str, dict] = {pid: {"neighbors": [], "sales": []} for pid in rows.PARCEL_ID}
    groups = {key: g.reset_index(drop=True) for key, g in r.groupby(["DOR_UC", "NBRHD_CD"], sort=False)}
    cgroups = {key: g.reset_index(drop=True) for key, g in comps.groupby(["DOR_UC", "NBRHD_CD"], sort=False)}
    for key, tg in rows.groupby(["DOR_UC", "NBRHD_CD"], sort=False):
        condo = key[0] == "004"
        ts, tl, tp = tg.sqft.to_numpy(float), tg.land.to_numpy(float), tg.PARCEL_ID.to_numpy(object)
        g = groups.get(key)
        if g is not None and len(g):
            recs = [{"parcel_id": x.PARCEL_ID, "address": s(x.PHY_ADDR1), "sqft": float(x.sqft),
                     "just_value": float(x.JV), "value_per_sqft": round(float(x.ppsf), 2)} for x in g.itertuples()]
            for pid, ix in zip(tp, _nearest(ts, tl, tp, g, p.size_band, p.land_band, condo, k)):
                out[pid]["neighbors"] = [recs[j] for j in ix]
        c = cgroups.get(key)
        if c is not None and len(c):
            recs = [{"parcel_id": x.PARCEL_ID, "address": s(x.PHY_ADDR1),
                     "sale_month": f"{int(x.SALE_YR)}-{int(x.SALE_MO):02d}", "price": float(x.SALE_PRC),
                     "price_adjusted_to_valuation_date": round(float(x.SALE_PRC * x.tadj), 0), "sqft": float(x.sqft),
                     "record": s(getattr(x, "CLERK_NO", None)) or s(getattr(x, "SALE_ID_CD", None))} for x in c.itertuples()]
            for pid, ix in zip(tp, _nearest(ts, tl, tp, c, p.comp_size_band, p.land_band, condo, k)):
                out[pid]["sales"] = [recs[j] for j in ix]
    return out
