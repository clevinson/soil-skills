# SSURGO Query Reference

Two keyless public APIs. Each is described as an HTTP request first; use whichever transport your runtime has — `curl` if you have a shell (Claude Code), Python if you're in a sandbox (ChatGPT, claude.ai). All SQL templates were tested live against SDA (2026-06-06).

## Network access required

These APIs are external. Skill sandboxes block outbound internet by default (only package-manager domains). If calls fail with a network/connection error, the host's domain allowlist must include — or be set to allow all domains:

- `geocoding.geo.census.gov`
- `sdmdataaccess.sc.egov.usda.gov`

In Claude Code's shell this is generally open. On claude.ai / ChatGPT, enable network access for the skill (allowlist the two domains above), then start a fresh conversation. If you cannot enable it, say so plainly — the skill cannot fabricate soil data.

## APIs

### Census Geocoder (address → coordinates)

**Request:** `GET https://geocoding.geo.census.gov/geocoder/locations/onelineaddress`
with query params `address={{URL_ENCODED_ADDRESS}}`, `benchmark=Public_AR_Current`, `format=json`

- Free, no key. **US addresses only** (fine — SSURGO is US-only).
- Success: `result.addressMatches[0].coordinates` → `x` = longitude, `y` = latitude; `matchedAddress` shows what was actually matched.
- Miss: `addressMatches` is `[]`. Common for campus buildings, PO boxes, new construction. Ask the user for a cross-street, city, or coordinates.

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

### Soil Data Access — SDA (all soil queries)

**Request:** `POST https://sdmdataaccess.sc.egov.usda.gov/Tabular/post.rest`
- Header: `Content-Type: application/json`
- Body (JSON): `{"query": "<SQL>", "format": "JSON+COLUMNNAME"}`
- Response: `{"Table": [[column names], [row1...], [row2...]]}` — first array is headers.
- **No rows → response is `{}`** (empty object, not an empty Table).

Universal: accepts T-SQL (SQL Server dialect), no key, no auth. It is a government SQL Server — occasionally slow or down; use a ~60s timeout, and on failure report honestly and offer to retry.

*Shell:* the body is a single-quoted JSON string, so escape single quotes inside SQL by doubling (`''`) and keep SQL on one line.
```bash
curl -s --max-time 60 -X POST "https://sdmdataaccess.sc.egov.usda.gov/Tabular/post.rest" \
  -H "Content-Type: application/json" \
  -d '{"query":"{{SQL_ON_ONE_LINE}}","format":"JSON+COLUMNNAME"}'
```
*Python:* pass a dict — `json.dumps` handles all escaping, and SQL may be multi-line. No shell quoting rules apply.
```python
import json, urllib.request
url = "https://sdmdataaccess.sc.egov.usda.gov/Tabular/post.rest"
body = json.dumps({"query": sql, "format": "JSON+COLUMNNAME"}).encode()
req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
resp = json.loads(urllib.request.urlopen(req, timeout=60).read())
rows = resp.get("Table", [])  # [] / no "Table" key = no rows
```

## Query templates

Substitute `{{lon}}`, `{{lat}}`, `{{mukey}}`. Longitude first in POINT — WKT order, the classic trap.

### Q1 — point → mukey

```sql
SELECT * FROM SDA_Get_Mukey_from_intersection_with_WktWgs84('POINT({{lon}} {{lat}})')
```

Returns one mukey for a point. Empty (`{}`) → outside SSURGO coverage (open water, unmapped).

### Q2 — map unit overview

```sql
SELECT m.mukey, m.musym, m.muname, m.muacres, m.farmlndcl,
       mag.drclassdcd, mag.wtdepannmin, mag.flodfreqdcd, mag.pondfreqprs,
       mag.hydclprs, mag.hydgrpdcd, mag.slopegraddcp, mag.brockdepmin, mag.aws0150wta
FROM mapunit m
LEFT JOIN muaggatt mag ON m.mukey = mag.mukey
WHERE m.mukey = {{mukey}}
```

| Column | Meaning |
|---|---|
| `muname` | Map unit name, e.g. "Reiff very fine sandy loam" |
| `farmlndcl` | Farmland classification (e.g. "Prime farmland if irrigated") |
| `drclassdcd` | Drainage class, dominant condition |
| `wtdepannmin` | Min annual water table depth, cm. `null` = none observed within 2 m |
| `flodfreqdcd` / `pondfreqprs` | Flooding freq (dominant) / ponding freq (% of unit) |
| `hydclprs` | % of map unit that is hydric soil |
| `hydgrpdcd` | Hydrologic soil group (A–D, runoff behavior) |
| `slopegraddcp` | Slope gradient %, dominant component |
| `brockdepmin` | Min depth to bedrock, cm. `null` = none within 2 m |
| `aws0150wta` | Available water storage 0–150 cm, cm (weighted avg) |

### Q3 — components & horizons

```sql
SELECT c.cokey, c.compname, c.comppct_r, c.majcompflag, c.taxclname,
       c.drainagecl, c.nirrcapcl, c.irrcapcl,
       ch.hzname, ch.hzdept_r, ch.hzdepb_r, ctg.texdesc,
       ch.ph1to1h2o_r, ch.om_r, ch.awc_r, ch.ksat_r
FROM component c
LEFT JOIN chorizon ch ON c.cokey = ch.cokey
LEFT JOIN chtexturegrp ctg ON ch.chkey = ctg.chkey AND ctg.rvindicator = 'Yes'
WHERE c.mukey = {{mukey}} AND c.comppct_r >= 10
ORDER BY c.comppct_r DESC, ch.hzdept_r
```

| Column | Meaning |
|---|---|
| `compname` / `comppct_r` | Soil series name / % of map unit |
| `taxclname` | Full taxonomic class, e.g. "Coarse-loamy, mixed, nonacid, thermic Mollic Xerofluvents" |
| `nirrcapcl` / `irrcapcl` | Land capability class, non-irrigated / irrigated (1–8) |
| `hzname`, `hzdept_r`, `hzdepb_r` | Horizon name, top & bottom depth (cm) |
| `texdesc` | Texture, e.g. "Very fine sandy loam" |
| `ph1to1h2o_r` | pH (1:1 water) |
| `om_r` | Organic matter % |
| `awc_r` | Available water capacity, cm/cm |
| `ksat_r` | Saturated hydraulic conductivity, µm/s |

`_r` suffix = representative value (vs `_l` low / `_h` high).

### Q3b — restrictive layers

```sql
SELECT c.compname, cr.reskind, cr.resdept_r
FROM component c
LEFT JOIN corestrictions cr ON c.cokey = cr.cokey
WHERE c.mukey = {{mukey}} AND c.comppct_r >= 10
```

`reskind` = kind of restriction (duripan, bedrock, etc.), `resdept_r` = depth (cm). All-null → no restrictive layer within 2 m.

### Q4 — interpretations & ratings

```sql
SELECT c.compname, c.comppct_r, ci.mrulename, ci.interphrc, ci.interphr
FROM component c
JOIN cointerp ci ON c.cokey = ci.cokey
WHERE c.mukey = {{mukey}} AND c.comppct_r >= 10
  AND ci.ruledepth = 0
  AND ci.mrulename IN (
    'ENG - Septic Tank Absorption Fields',
    'ENG - Dwellings With Basements',
    'ENG - Dwellings W/O Basements',
    'ENG - Local Roads and Streets',
    'ENG - Lawn, Landscape, Golf Fairway',
    'ENG - Shallow Excavations',
    'NCCPI - National Commodity Crop Productivity Index (Ver 3.0)'
  )
ORDER BY c.comppct_r DESC, ci.mrulename
```

- `ruledepth = 0` → the overall rating (deeper rows are sub-rules; for "what limitation drives this," query `ruledepth > 0` for the same `mrulename` and `cokey`).
- `interphrc` = rating class text; `interphr` = numeric 0 (no limitation) → 1 (severe) for ENG rules; for NCCPI it is the productivity index 0→1 (higher = better).
- **Rule names must match exactly** — they are finicky strings.

### D — discover available interpretations

Interpretation availability varies by survey area (state-specific ones exist). To see what a map unit has:

```sql
SELECT DISTINCT ci.mrulename
FROM component c JOIN cointerp ci ON c.cokey = ci.cokey
WHERE c.mukey = {{mukey}} ORDER BY ci.mrulename
```

Notable finds (confirmed in CA): `'AGR - California Revised Storie Index (CA)'`, `'VIN - Vinifera Wine Grape Site Desirability (Long)'` and other VIN rules, `'URB/REC - Camp Areas'`, `'URB/REC - Playgrounds'`, `'ENG - Ground-based Solar Arrays, Soil-based Anchor Systems'`, `'SOH - Soil Susceptibility to Compaction'`. Use these for user questions beyond the curated set (vineyards, solar farms, campgrounds...).

## Area, compare & series modes

### AQ — area-weighted soils over an AOI (polygon or radius)

Use when the user wants the soils across a *parcel/area*, not a single point. Build the AOI as one WKT polygon, then run AQ (the AOI WKT is inlined twice). Geometry is used for the intersection; the result is cast to geography to get acres.

Getting `{{aoi_wkt}}`:
- **User pasted WKT polygon** → use as-is.
- **User pasted GeoJSON** → convert the ring to WKT: `POLYGON((lon lat, lon lat, ...))` (GeoJSON coords are `[lon, lat]`; close the ring by repeating the first point).
- **Radius around the geocoded point** (no polygon given) → build a circle polygon client-side. SDA does **not** allow `DECLARE`, so don't build it in SQL — pass a literal polygon.

```python
import math
def circle_wkt(lon, lat, radius_m=150, n=32):
    dlat = radius_m / 111320.0
    dlon = radius_m / (111320.0 * math.cos(math.radians(lat)))
    pts = [(lon + dlon*math.cos(2*math.pi*i/n), lat + dlat*math.sin(2*math.pi*i/n)) for i in range(n)]
    pts.append(pts[0])
    return "POLYGON((" + ", ".join(f"{x} {y}" for x, y in pts) + "))"
```

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

Returns each intersecting map unit with intersected acreage. Compute each unit's % of the AOI from the acres. Then for the dominant unit(s), run Q2/Q3/Q4 with their `mukey` for the usual detail. `0.000247105` converts m² → acres. If geography `STArea` errors on a self-intersecting / badly-oriented AOI, report it rather than guessing.

### Compare mode

No new SQL — run the full point workflow (Q1 → Q2/Q3/Q3b/Q4) for each location, then present a side-by-side table of the key properties and interpretations, followed by a short narrative diff.

### SQ — series lookup (by name, not location)

Use when the user names a soil series ("tell me about the Yolo series"). Summarize its taxonomy and extent across the database:

```sql
SELECT TOP 5 c.taxclname, c.drainagecl, COUNT(*) AS n_components, SUM(c.comppct_r) AS pct_sum
FROM component c
WHERE c.compname = '{{series}}' AND c.majcompflag = 'Yes'
GROUP BY c.taxclname, c.drainagecl
ORDER BY n_components DESC
```

For a representative profile, take one major component and run the Q3 horizon query against its `cokey`:
```sql
SELECT TOP 1 c.cokey FROM component c
WHERE c.compname = '{{series}}' AND c.majcompflag = 'Yes'
ORDER BY c.comppct_r DESC
```
Link to the official series description: `https://soilseries.sc.egov.usda.gov/OSD_Docs/<FIRST-LETTER>/<SERIES-UPPER>.html`, and UC Davis SoilWeb: `https://casoilresource.lawr.ucdavis.edu/sde/?series=<series>`. A series spans many map units nationwide — this is a representative summary, not a single mapped instance.

## Table relationships (for ad-hoc queries)

```
mapunit (mukey) ──< component (cokey)  [comppct_r = % of map unit]
                       ├──< chorizon (chkey)        [horizons, ordered by hzdept_r]
                       │       └──< chtexturegrp    [use rvindicator = 'Yes']
                       ├──< cointerp                [interpretations; filter ruledepth = 0]
                       └──< corestrictions          [restrictive layers]
mapunit (mukey) ──  muaggatt                        [pre-aggregated map unit attributes]
```

A map unit is the SSURGO polygon; it usually contains several components (soils). Report the dominant component in full, name the rest with percentages.

## Glossaries

**Drainage classes** (wettest → driest): Very poorly drained · Poorly drained · Somewhat poorly drained · Moderately well drained · Well drained · Somewhat excessively drained · Excessively drained.

**Hydrologic soil groups:** A = low runoff, high infiltration (sands) · B = moderate · C = slow infiltration · D = high runoff (clays, shallow, high water table). Dual codes like C/D = drained/undrained condition.

**Land capability class:** 1 = few limitations, prime for cultivation → 8 = no agricultural use. Subclass letters: e = erosion, w = wetness, s = shallow/stony/sandy, c = climate.

**Interpretation rating classes:** Not limited → Somewhat limited → Very limited. "Very limited" ≠ impossible; it means significant engineering/mitigation cost. NCCPI classes run from "Low inherent productivity" to "High inherent productivity."

**Farmland classification:** "All areas are prime farmland" · "Prime farmland if irrigated" (and other conditional variants) · "Farmland of statewide importance" · "Not prime farmland".

**Common non-soil map units:** `Water` · `Urban land` (often a complex, e.g. "Urban land-Xerorthents complex") · `NOTCOM` (survey not complete) · `Pits/Dumps`. Report these honestly — there is no soil data to interpret.

**Units cheat sheet:** depths cm · Ksat µm/s (10 µm/s ≈ 1.4 in/hr) · AWC cm/cm · OM % · pH in 1:1 water.
