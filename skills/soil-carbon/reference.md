# Soil Carbon Query Reference

Estimates soil carbon stock from USDA SSURGO — **organic** (SOC, from organic matter) and **inorganic** (SIC, from carbonates) — computed transparently from horizon data. Two keyless public APIs; call them with `curl` (shell) or Python (sandbox). Tested live against SDA (2026-06-07).

## Network access required

External APIs. Skill sandboxes block outbound internet by default. If calls fail with a network error, the host's domain allowlist must include — or allow all domains:

- `geocoding.geo.census.gov`
- `sdmdataaccess.sc.egov.usda.gov`

On claude.ai / ChatGPT, enable network access, allowlist the two domains, then start a fresh conversation. Never fabricate carbon values if you cannot reach the APIs — say so.

## APIs

### Census Geocoder (address → coordinates)

**Request:** `GET https://geocoding.geo.census.gov/geocoder/locations/onelineaddress`
with query params `address={{URL_ENCODED_ADDRESS}}`, `benchmark=Public_AR_Current`, `format=json`

- Success: `result.addressMatches[0].coordinates` → `x` = longitude, `y` = latitude.
- Miss: `addressMatches` is `[]` → ask for a cross-street or coordinates.

*Shell:*
```bash
curl -s "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress?address={{URL_ENCODED_ADDRESS}}&benchmark=Public_AR_Current&format=json"
```
*Python:*
```python
import json, urllib.parse, urllib.request
params = urllib.parse.urlencode({"address": address, "benchmark": "Public_AR_Current", "format": "json"})
url = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress?" + params
resp = json.loads(urllib.request.urlopen(url, timeout=60).read())
matches = resp["result"]["addressMatches"]  # [] = no match
```

### Soil Data Access — SDA

**Request:** `POST https://sdmdataaccess.sc.egov.usda.gov/Tabular/post.rest`
- Header: `Content-Type: application/json`
- Body (JSON): `{"query": "<SQL>", "format": "JSON+COLUMNNAME"}`
- Response: `{"Table": [[column names], [row...]]}`; `{}` if no rows.

*Shell:* single-quoted JSON body, so double single-quotes inside SQL (`''`) and keep SQL on one line.
```bash
curl -s --max-time 60 -X POST "https://sdmdataaccess.sc.egov.usda.gov/Tabular/post.rest" \
  -H "Content-Type: application/json" \
  -d '{"query":"{{SQL_ON_ONE_LINE}}","format":"JSON+COLUMNNAME"}'
```
*Python:* pass a dict; `json.dumps` escapes; SQL may be multi-line.
```python
import json, urllib.request
url = "https://sdmdataaccess.sc.egov.usda.gov/Tabular/post.rest"
body = json.dumps({"query": sql, "format": "JSON+COLUMNNAME"}).encode()
req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
resp = json.loads(urllib.request.urlopen(req, timeout=60).read())
rows = resp.get("Table", [])
```

## Query templates

### Q1 — point → mukey

```sql
SELECT * FROM SDA_Get_Mukey_from_intersection_with_WktWgs84('POINT({{lon}} {{lat}})')
```

⚠️ WKT order is `POINT(lon lat)` — longitude first. Empty `{}` → outside SSURGO coverage (water/unmapped): say so.

### CQ — carbon inputs by horizon

Pulls everything the carbon computation needs — **organic** (`om_r`), **inorganic** (`caco3_r`), and the map unit kind (`mukind`) that decides how to report (see "Reporting by map unit kind"). Coarse-fragment volume is summed from the child `chfrags` table via a correlated subquery (joining `chfrags` directly would multiply horizon rows).

```sql
SELECT c.compname, c.comppct_r, c.majcompflag,
       (SELECT mukind FROM mapunit WHERE mukey = {{mukey}}) AS mukind,
       ch.hzname, ch.hzdept_r, ch.hzdepb_r,
       ch.om_l, ch.om_r, ch.om_h,
       ch.caco3_l, ch.caco3_r, ch.caco3_h,
       ch.dbthirdbar_r,
       (SELECT SUM(cf.fragvol_r) FROM chfrags cf WHERE cf.chkey = ch.chkey) AS fragvol_r
FROM component c
JOIN chorizon ch ON c.cokey = ch.cokey
WHERE c.mukey = {{mukey}} AND c.comppct_r >= 10
ORDER BY c.comppct_r DESC, ch.hzdept_r
```

| Column | Meaning |
|---|---|
| `compname` / `comppct_r` | Soil series / % of map unit |
| `majcompflag` | "Yes" = major component |
| `mukind` | Map unit kind: Consociation / Complex / Association / Undifferentiated group (drives reporting) |
| `hzdept_r`, `hzdepb_r` | Horizon top & bottom depth (cm) |
| `om_l` / `om_r` / `om_h` | Organic matter %, low / representative / high → organic carbon |
| `caco3_l` / `caco3_r` / `caco3_h` | Calcium carbonate equivalent %, low / rep / high → inorganic carbon (null = none) |
| `dbthirdbar_r` | Bulk density at ⅓ bar, g/cm³ (representative) |
| `fragvol_r` (summed) | Coarse fragment volume, % (null = none) |

`_l` / `_h` are SSURGO's stated low/high for the property across the component — used for the uncertainty band (see below). They are **not** a confidence interval.

## Carbon computation

Two pools — report both, plus their sum (total soil carbon). The formula below gives **one component's** stock from its horizons; *which* component(s) you report at a point depends on the map unit kind — see "Reporting by map unit kind" below. For each horizon, with thickness clipped to the target depth (e.g. for 0–100 cm, a 80–130 cm horizon contributes only 20 cm) and `(1 − fragvol/100)` removing coarse-fragment volume that holds no fine-earth carbon:

**Organic (SOC):**
1. Organic carbon: `OC% = om_r / 1.724` — the van Bemmelen factor (organic matter → organic carbon).
2. Horizon stock (t C/ha): `OC% × dbthirdbar_r × thickness_cm × (1 − fragvol/100)`.

**Inorganic (SIC):**
1. Carbonate carbon: `IC% = caco3_r × 0.1200` — CaCO₃ is 12.0% carbon by mass (12.01 / 100.09 g·mol⁻¹), assuming carbonate is calcite.
2. Horizon stock (t C/ha): `IC% × dbthirdbar_r × thickness_cm × (1 − fragvol/100)`.

Dimensional check (both): %(g C/100 g) × (g/cm³) × cm over 1 ha = Mg C/ha.

**Totals:** sum each pool over horizons to **0–30 cm** (IPCC / standard reporting depth) and **0–100 cm** (fuller profile). Total soil carbon = SOC + SIC. Report SOC, SIC, and total separately — they behave very differently (see caveats).

Skip horizons with null `dbthirdbar_r` (or, for a given pool, null `om_r` / `caco3_r`) and flag them — do not guess. Treat null `caco3_r` or `fragvol_r` as 0.

### Reporting by map unit kind (point mode)

A map unit is not always one soil. `mukind` (from CQ) decides how to report a point honestly — rather than blending dissimilar soils into a number that describes none of them:

The real trigger is **how many major components (≥10%) the map unit actually has**, with `mukind` as the guide:

- **Consociation** (~62% of US map units): one soil dominates. Report a **single headline** carbon for the dominant component; the per-horizon table illustrates it.
- **Complex / Association / Undifferentiated group with ≥2 components ≥10%**: two or more *dissimilar* soils, and SSURGO does **not** say which one is at a given point. Do **not** report a single point value. Instead show a per-component table (component · % · SOC · SIC · total `[band]`) and give an honest **range** across the components — "≈ X–Y t C/ha depending which of these soils is at your spot." Use the dominant component's horizons as the worked illustration.
- **Only one component ≥10%** (whatever the `mukind` — some complexes/undifferentiated groups resolve to a single major soil with sub-10% minors): treat it like a consociation — report that component as the headline, and note the minor components exist below the 10% cutoff.
- **Null `mukind`** (rare): same logic — one major component → headline; two or more → components + range.
- **Non-soil** map unit (e.g. Urban land, Water) with no horizon data: report that there is **no soil carbon to estimate**, not zero.

Area mode is different and does aggregate across components and map units (see "Area mode") — there, integrating real ground in real proportions is legitimate; the blend describes actual carbon on the landscape, not a guess about one spot.

### Uncertainty band

Report each figure as `representative [low – high]`. Compute **low** by using `om_l` and `caco3_l` in place of the `_r` values, and **high** with `om_h` / `caco3_h` — holding bulk density and fragments at representative. Carbon-stock uncertainty is dominated by the organic-matter (and carbonate) concentration range; bulk density's range adds only a few percent and its `_l`/`_h` are not physically paired with the OM extremes (in SSURGO, `om_h` may sit with `dbthirdbar_h`, the opposite of real soils), so do not combine all-low/all-high — vary only the carbon concentration.

**State plainly what the band is and isn't.** It is the range implied by **SSURGO's own low/high organic-matter and carbonate estimates** for this map-unit component. It is **NOT** a statistical confidence interval (the L/H carry no stated probability), and it does **NOT** include the errors that often dominate:

- *which* component you actually have at this point (for a consociation we report the dominant soil; for a complex/association we show each component because SSURGO can't place them — but even within a consociation, minor components differ);
- map-delineation / positional uncertainty (whether the point is even in the right polygon);
- bulk-density and coarse-fragment uncertainty (held at representative here);
- temporal change, management, land-use history, and lab/pedon measurement error.

So **true uncertainty is wider than this band** — present it as "SSURGO's stated property range," never as a guarantee.

### Worked examples (tested live)

**Zamora loam, Davis CA (mukey 459310)** — non-calcareous, SIC ≈ 0:

| Horizon | Depth cm | OM% | OC% | CaCO₃% | BD | Frag% | SOC t C/ha |
|---|---|---|---|---|---|---|---|
| H1 | 0–25 | 3.0 | 1.74 | 0 | 1.48 | 0 | 64.4 |
| H2 | 25–102 | 0.75 | 0.435 | 0 | 1.40 | 0 | 45.7 (to 100 cm) |

→ 0–30 cm: **SOC 67 [45–90], SIC 0, total 67 [45–90]** · 0–100 cm: **SOC 110 [73–147], SIC 0, total 110 [73–147]** t C/ha. The ±33% band comes entirely from SSURGO's OM low/high (e.g. H1 om 2–4%).

**Harkey, near Las Cruces NM (mukey 634572)** — calcareous; SIC is ~40% of total:

| Horizon | Depth cm | OM% | CaCO₃% | BD | SOC | SIC |
|---|---|---|---|---|---|---|
| H1 | 0–30 | 0.9 | 3 | 1.50 | — | — |
| H2 | 30–152 | 0.9 | 3 | 1.45 | — | — |

→ 0–30 cm: **SOC 23.5, SIC 16.2, total 39.7** · 0–100 cm: **SOC 76.5, SIC 52.7, total 129.2** t C/ha.

### Python helper (optional)

```python
def carbon_stock(horizons, depth_limit_cm, om_key="om_r", caco3_key="caco3_r"):
    """horizons: dicts with hzdept_r, hzdepb_r, dbthirdbar_r, fragvol_r, and the om/caco3 keys.
    Returns (soc, sic, gaps) in tonnes C/ha. Pass om_l/caco3_l (or _h) for the band."""
    soc = sic = 0.0
    gaps = []
    for h in horizons:
        top, bot = h["hzdept_r"], h["hzdepb_r"]
        bd = h["dbthirdbar_r"]
        if top is None or bot is None or bd is None:
            if not (top is None or bot is None):
                gaps.append(h.get("hzname"))
            continue
        bot = min(bot, depth_limit_cm)
        if bot <= top:
            continue
        vol = bd * (bot - top) * (1 - (h["fragvol_r"] or 0.0) / 100.0)
        if h.get(om_key) is not None:
            soc += (h[om_key] / 1.724) * vol
        sic += ((h.get(caco3_key) or 0.0) * 0.12) * vol
    return soc, sic, gaps

# per-component stock + band (CQ already returns every component >=10%, so this is free)
def components_carbon(rows, depth):
    comps = {}
    for r in rows:
        comps.setdefault((r["compname"], r["comppct_r"]), []).append(r)
    out = []
    for (name, pct), hz in comps.items():
        soc, sic, _ = carbon_stock(hz, depth)
        lo = sum(carbon_stock(hz, depth, "om_l", "caco3_l")[:2])   # SOC+SIC low
        hi = sum(carbon_stock(hz, depth, "om_h", "caco3_h")[:2])   # SOC+SIC high
        out.append({"component": name, "pct": pct, "soc": soc, "sic": sic,
                    "total": soc + sic, "low": lo, "high": hi})
    return sorted(out, key=lambda d: -d["pct"])

comps = components_carbon(rows, 30)
# Consociation -> report comps[0] (dominant) as the single headline.
# Complex/Association/Undifferentiated -> report all comps; honest range = (min total, max total).
# Area mode -> component-weighted map-unit mean = sum(c['pct']*c['total']) / sum(c['pct']).
```

## Area mode (carbon over a parcel/AOI)

For "how much carbon is in this parcel," area-weight the per-point estimate across all map units intersecting an AOI.

1. **Build the AOI as one WKT polygon** — user-pasted WKT → use as-is; GeoJSON → convert the ring to `POLYGON((lon lat, ...))` (GeoJSON is `[lon, lat]`; close the ring); no polygon → a radius circle around the geocoded point:

   ```python
   import math
   def circle_wkt(lon, lat, radius_m=150, n=32):
       dlat = radius_m / 111320.0
       dlon = radius_m / (111320.0 * math.cos(math.radians(lat)))
       pts = [(lon + dlon*math.cos(2*math.pi*i/n), lat + dlat*math.sin(2*math.pi*i/n)) for i in range(n)]
       pts.append(pts[0])
       return "POLYGON((" + ", ".join(f"{x} {y}" for x, y in pts) + "))"
   ```

2. **Intersect with SSURGO** to get each map unit's intersected acreage (inline the AOI WKT twice; SDA forbids `DECLARE`):

   ```sql
   SELECT mu.mukey, mu.muname,
     SUM(GEOGRAPHY::STGeomFromText(
           mp.mupolygongeo.STIntersection(GEOMETRY::STGeomFromText('{{aoi_wkt}}',4326)).STAsText(), 4326
         ).STArea() * 0.000247105) AS acres
   FROM mupolygon mp JOIN mapunit mu ON mu.mukey = mp.mukey
   WHERE mp.mupolygongeo.STIntersects(GEOMETRY::STGeomFromText('{{aoi_wkt}}',4326)) = 1
   GROUP BY mu.mukey, mu.muname
   ORDER BY acres DESC
   ```

3. **For each map unit**, run CQ with its `mukey` and compute a **component-weighted** stock (rep + band) — `stock_unit = Σ(comppct_i × total_i) / Σ(comppct_i)` over its components (`components_carbon` above). Unlike point mode, area mode *does* blend components, because you're integrating real ground in real proportions — `mukind` does not gate this.

4. **Aggregate across map units** (per pool, and for low/high):
   - **Area-weighted mean stock** (t C/ha) = `Σ(acres_i × stock_unit_i) / Σ(acres_i)`.
   - **Total stock** (t C, the absolute amount in the AOI) = `Σ(stock_unit_i × acres_i × 0.404686)` — `0.404686` is ha per acre, since stock is t C/ha.

   Report the per-map-unit table (unit · acres · t C/ha), then the area-weighted mean `rep [low–high]` and the total tonnes. (A prior dominant-component-only test of the 150 m Davis circle gave mean 61 [43–79], total 427 t C over 7.0 ha; component-weighting shifts these modestly.)

   Components with no horizon data (miscellaneous areas — Rock outcrop, Water) contribute ~0 carbon; if they're a non-trivial share of a map unit, say so rather than silently dropping them.

## Caveats (always surface)

- SSURGO values are **representative/estimated**, not measured at this point. These are **modeled baselines**, not field measurements.
- The **uncertainty band is SSURGO's stated OM/carbonate range, not a confidence interval**, and excludes the component-choice, positional, bulk-density, and temporal errors that often dominate — true uncertainty is wider (see "Uncertainty band" above).
- **SOC and SIC are not interchangeable.** Organic carbon is biologically active and management-sensitive (tillage, cover crops, land-use change shift it on yearly–decadal scales). Inorganic carbon (pedogenic/lithogenic carbonate) is a large, slow pool that turns over on millennial timescales; whether its formation is a net climate sink or source depends on the cation and bicarbonate source, so do not present SIC as readily "sequesterable." Keep them separate.
- `caco3_r` is **calcium carbonate equivalent** — it does not distinguish pedogenic (formed in place) from inherited/lithogenic carbonate, and the ×0.12 factor assumes calcite (dolomite would differ slightly).
- SSURGO is 1:24,000-scale mapping: it describes soils **mapped in this area**, not this exact spot.
- For measured carbon you'd need lab data (KSSL) or on-site sampling — out of scope here.

## Units

OM/OC and CaCO₃/IC in % by weight · bulk density g/cm³ · depth cm · carbon stock t C/ha (= Mg C/ha). 1 t C/ha = 0.1 kg C/m². To CO₂-equivalent: × 3.67.
