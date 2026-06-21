# SSURGO Query Reference

Keyless public HTTP services. Each is described as a request first; use whichever transport your runtime has — `curl` if you have a shell (Claude Code), Python if you're in a sandbox (ChatGPT, claude.ai). The **core** (geocode + soils) is the SQL templates, tested live against SDA (2026-06-06). The **context layers** (parcel, water, flood, elevation — see "Beyond soils") are nationally-general ArcGIS REST endpoints, tested live 2026-06-20.

## Network access & host roster

These are external services; sandboxes (claude.ai, ChatGPT) block outbound internet by default (only package-manager domains). Allowlist **by capability** — and treat the list as **roles, not frozen hosts**: parcel and wetland services in particular migrate, so confirm the live service root (`?f=json`) before relying on one.

| Capability | Host(s) | Needed for |
|---|---|---|
| Geocode | `geocoding.geo.census.gov` | address → point (**core**) |
| Soils | `sdmdataaccess.sc.egov.usda.gov` | all SSURGO queries (**core**) |
| Parcels | statewide/county ArcGIS host (varies) — or keyed national (Regrid/ReportAll) | PQ parcel boundary |
| Hydrography + watershed | `hydro.nationalmap.gov` | HQ (NHD), WQ (WBD/HUC12) |
| Elevation | `elevation.nationalmap.gov` | EQ (3DEP) |
| Flood | `hazards.fema.gov` | FQ (FEMA NFHL) |
| Wetlands | USFWS NWI host (migrating — verify) | NW |

In Claude Code's shell these are generally open. On claude.ai / ChatGPT, allowlist the capabilities the question needs, then start a fresh conversation. If you can't, say so plainly — never fabricate data.

### Preflight (run before building the workflow)

Decide the programmatic-vs-degraded path *up front*, not one dead-end at a time. Probe only the hosts the chosen path needs and report which tiers will run:

```python
import urllib.request, urllib.error
def reachable(host, timeout=8):
    try:
        urllib.request.urlopen("https://" + host, timeout=timeout); return True
    except urllib.error.HTTPError:
        return True                      # responded (even 4xx) = reachable
    except Exception:
        return False                     # connection refused/blocked
HOSTS = {"geocode": "geocoding.geo.census.gov", "soils": "sdmdataaccess.sc.egov.usda.gov",
         "hydro": "hydro.nationalmap.gov", "flood": "hazards.fema.gov", "elevation": "elevation.nationalmap.gov"}
status = {k: reachable(h) for k, h in HOSTS.items()}
# e.g. report: "parcel + soils will run here; NHD and FEMA need their hosts allowlisted."
```

When a needed host is blocked, use **Graceful degradation** (end of "Beyond soils") — a parameterized URL the user can open + an offer to ingest the pasted result. Never silently guess.

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

## Geometry helpers (`geo.py`)

`geo.py` (this skill's directory) is the one tested path from whatever boundary the user has to the AOI WKT that Area mode consumes. **Use it instead of re-implementing GeoJSON↔WKT inline** — getting lon/lat order or ring orientation wrong fails *silently* until `STArea`/`STIntersection` throws. Coordinates are always **(lon, lat), WGS84 — longitude first**.

- `to_aoi_wkt(source)` — ingest **GeoJSON** (dict or text), **WKT**, or a **zipped shapefile** path → one validated AOI WKT polygon (rings closed, exterior CCW, multipolygon reduced to its largest part). Also accepts a pasted blob directly (the graceful-degradation path).
- `validate_and_repair(wkt)` — close/orient rings; if `shapely` is importable, also fixes self-intersections via `make_valid`; raises visibly if unrepairable.
- `approx_acres(aoi)` — cheap local shoelace estimate (WKT or GeoJSON). **Run before spending an SDA round-trip** — catches a malformed or lon/lat-swapped polygon early. Verified to match SDA's geographic area within ~1% on parcel-scale AOIs.
- `geojson_ring_to_wkt(ring)` — the single-ring conversion, as a function.

```python
import geo
aoi_wkt = geo.to_aoi_wkt(pasted_geojson_or_wkt)   # or geo.circle_wkt(lon, lat, radius_m) below
if not (0.01 < geo.approx_acres(aoi_wkt) < 5_000_000):
    ...  # implausible area → likely swapped coords or a bad ring; stop and report
```

## Area, compare & series modes

### AQ — area-weighted soils over an AOI (polygon or radius)

Use when the user wants the soils across a *parcel/area*, not a single point. Build the AOI as one WKT polygon (via `geo.to_aoi_wkt`), sanity-check it with `geo.approx_acres`, then run AQ (the AOI WKT is inlined three times). Geometry is used for the intersection; the clipped result is cast to geography for acres **and emitted as WKT** so you have the per-unit polygons without another round-trip.

Getting `{{aoi_wkt}}`:
- **User pasted WKT / GeoJSON, or a zipped shapefile** → `geo.to_aoi_wkt(source)`.
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
      ).STArea() * 0.000247105) AS acres,
  GEOMETRY::STGeomFromText('{{aoi_wkt}}',4326).STIntersection(
        GEOMETRY::UnionAggregate(mp.mupolygongeo)).STAsText() AS clipped_wkt
FROM mupolygon mp JOIN mapunit mu ON mu.mukey = mp.mukey
WHERE mp.mupolygongeo.STIntersects(GEOMETRY::STGeomFromText('{{aoi_wkt}}',4326)) = 1
GROUP BY mu.mukey, mu.muname
ORDER BY acres DESC
```

Returns each intersecting map unit with intersected acreage **and `clipped_wkt`** — its polygon (POLYGON or MULTIPOLYGON) clipped to the AOI [tested 2026-06-20]. Compute each unit's % of the AOI from the acres. Then for the dominant unit(s), run Q2/Q3/Q4 with their `mukey` for the usual detail. `0.000247105` converts m² → acres. If geography `STArea` errors on a self-intersecting / badly-oriented AOI, repair with `geo.validate_and_repair` first, else report it rather than guessing.

### Area-mode outputs (default, not optional)

The clipped geometry is in the AQ result — surface it by default:

- **Map.** Render a choropleth of the soil map units clipped to the AOI (color by `muname`), optionally overlaying context layers (NHD flowline, NWI/hydric wet pockets, FEMA zone). A nine-row table becomes the thing people actually want to see.
- **Downloadable deliverable.** Write the AOI + intersected soil units (and any fetched context layers) as **GeoJSON and/or a zipped shapefile** — WGS84, and for shapefile include a `.prj`. Users are usually headed to WSS / QGIS next; hand them the geometry. Each row's `clipped_wkt` → a GeoJSON Feature carrying that map unit's attributes (muname, mukey, acres).

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

## Beyond soils: parcel boundary & context layers (ArcGIS REST)

Soil questions almost always reach one hop past soils — "where's the parcel line," "is there a creek," "flood risk." These come from **ArcGIS REST `/query` endpoints**, which all share one mechanic. Learn the pattern once; use the tested national templates below. Same discipline as the SQL templates: **use a template when one fits; never fabricate** — if a field or code wasn't returned, don't infer it (e.g. don't call a stream perennial without its FCode).

### The ArcGIS REST pattern (one shape, all layers)

A feature layer lives at `<service>/<layerId>`. Two operations:

1. **Inspect schema first** when field names matter (they vary wildly): `GET <service>/<layerId>?f=json` → read `fields[].name`. Or one loose probe: `<service>/<layerId>/query?where=1=1&resultRecordCount=1&f=json` and look at the returned `attributes`.
2. **Query**: `GET <service>/<layerId>/query` with
   - attribute filter `where=<FIELD> LIKE '%...%'` (URL-encode), **or** spatial filter `geometry=<x,y | xmin,ymin,xmax,ymax | polygon-json>&geometryType=esriGeometryPoint|Envelope|Polygon&inSR=4326&spatialRel=esriSpatialRelIntersects`,
   - always `outFields=<comma list>&outSR=4326&returnGeometry=false&f=json` (`returnGeometry=true` only when you need the shape).

Response `{"features":[{"attributes":{...},"geometry":{...}}, ...]}`; no match → `"features": []`.

```python
import json, urllib.parse, urllib.request
def arcgis_query(service, layer, params, timeout=40):
    url = f"{service}/{layer}/query?" + urllib.parse.urlencode({"outSR": 4326, "f": "json", **params})
    return json.loads(urllib.request.urlopen(url, timeout=timeout).read()).get("features", [])
```

### PQ — parcel boundary from address / parcel ID

Address → boundary should be as routine as address → point. **There is no keyless *national* parcel `/query`** (Regrid, ReportAll cover the US but are key-gated), so use a documented **tier order** and state which tier answered:

- **Tier 1 — national parcel layer (optional, keyed).** Regrid / ReportAll if you have a key; else skip.
- **Tier 2 — statewide parcel layer (the realistic keyless default).** Most states publish one standardized ArcGIS parcel service. **Discover, don't hardcode:** search "<state> statewide parcels ArcGIS REST", then **inspect the layer schema** to find the address/owner field — names are wildly inconsistent (`SitusAddr`, `PARCELADDR`, `AddressLine1`, `Location`, `MBL`, `Owner`, `OWNER_NAME`…).
- **Tier 3 — county/municipal viewer.** Same discover-then-inspect procedure; last resort.

The portable asset is the **inspect-then-query two-step**, verified live (Montana statewide cadastral, `https://gisservicemt.gov/arcgis/rest/services/MSDI_Framework/Parcels/MapServer/0`): there the address field is `AddressLine1` and acreage is `GISAcres` — a different schema than any other state, which is exactly why you inspect first. Procedure:

1. `GET <parcelLayer>?f=json` → read `fields` → pick the address/owner field (call it `ADDR`).
2. `arcgis_query(service, layerId, {"where": "<ADDR> LIKE '%<number+street>%'", "outFields": "*", "returnGeometry": "true"})`.
3. Take the matching feature's geometry → `geo.to_aoi_wkt()` → feed Area mode's `{{aoi_wkt}}`.

Surface the caveat: a parcel polygon is a *cadastral* boundary of varying currency/precision, not a survey.

### HQ — hydrography (streams, creeks, ponds) — USGS NHD  *[tested]*

`service = https://hydro.nationalmap.gov/arcgis/rest/services/nhd/MapServer`
Large-scale layers: **6 = Flowline** (streams/rivers/canals), **12 = Waterbody** (lakes/ponds), 2 = Line.

```python
feats = arcgis_query("https://hydro.nationalmap.gov/arcgis/rest/services/nhd/MapServer", 6, {
    "geometry": "{xmin},{ymin},{xmax},{ymax}", "geometryType": "esriGeometryEnvelope",
    "inSR": 4326, "spatialRel": "esriSpatialRelIntersects",
    "outFields": "gnis_name,fcode,ftype", "returnGeometry": "false"})
```

Return `gnis_name` (named vs unnamed) and `fcode`/`ftype`. **FCode glossary** (don't interpret from memory):
- 46006 Stream/River **perennial** · 46003 **intermittent** · 46007 **ephemeral** · 46000 unspecified
- 55800 Artificial Path · 33600 Canal/Ditch · 33400 Connector
- Waterbody: 39004 Lake/Pond perennial · 39009 intermittent · 43600 Reservoir · 49300 Estuary
- FType: 460 StreamRiver · 558 ArtificialPath · 336 CanalDitch · 390 LakePond · 436 Reservoir · 466 SwampMarsh

NHD is ~1:24,000; small headwater/ephemeral channels may be absent. This template answers "is there a creek on the parcel" in one call.

### WQ — watershed (HUC12) — USGS WBD  *[tested]*

`service = https://hydro.nationalmap.gov/arcgis/rest/services/wbd/MapServer`, layer **6 = 12-digit HU (Subwatershed)** (5 = 10-digit). Point-in-poly:

```python
arcgis_query("https://hydro.nationalmap.gov/arcgis/rest/services/wbd/MapServer", 6, {
    "geometry": "{lon},{lat}", "geometryType": "esriGeometryPoint", "inSR": 4326,
    "spatialRel": "esriSpatialRelIntersects", "outFields": "huc12,name", "returnGeometry": "false"})
```

Returns `huc12` + `name` — the subwatershed the parcel drains into (e.g. `180201620504`, "Putah Creek-South Fork Putah Creek").

### FQ — flood zones — FEMA NFHL  *[tested]*

`service = https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer`, layer **28 = Flood Hazard Zones**. Intersect the AOI; return `FLD_ZONE, ZONE_SUBTY, SFHA_TF`. **Zone glossary:**
- `SFHA_TF` = `T` → in the **Special Flood Hazard Area** (1 %/yr, "100-year"); `F` → not.
- A, AE, AH, AO, AR, A99 = SFHA (AE carries base flood elevations) · V, VE = coastal high-hazard SFHA
- X with `ZONE_SUBTY "0.2 PCT ANNUAL CHANCE FLOOD HAZARD"` = 0.2 %/yr ("500-year", shaded X) · X "AREA OF MINIMAL FLOOD HAZARD" = unshaded X · D = undetermined

Cross-check against SSURGO's `flodfreqdcd` (Q2) — same question, independent sources. Caveat: cite the FIRM **effective date**; not all areas have modernized NFHL coverage.

### NW — wetlands — USFWS National Wetlands Inventory  *[role — verify host]*

The NWI public map-service host is **migrating** — the older `*.wim.usgs.gov` / `fws.gov/wetlands` endpoints now redirect or 500 (confirmed 2026-06-20). Discover the current `Wetlands/MapServer` root via the NWI Wetlands Mapper before use; the wetland-polygon layer carries `WETLAND_TYPE` / `ATTRIBUTE` (Cowardin code). **Until the host is confirmed, SSURGO's own `hydclprs` (hydric %, in Q2) is the primary wetland-adjacent signal** — NWI is a regulatory cross-check, not the only source.

### EQ — elevation / slope — USGS 3DEP  *[tested]*

`service = https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer`. Point elevation via `identify` — the point geometry **must** carry its spatialReference or you get `NoData`:

```python
g = urllib.parse.quote(json.dumps({"x": lon, "y": lat, "spatialReference": {"wkid": 4326}}))
url = ("https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer/identify"
       f"?geometry={g}&geometryType=esriGeometryPoint&returnGeometry=false&f=json")
elev_m = json.loads(urllib.request.urlopen(url, timeout=30).read())["value"]   # metres
```

Use to confirm/refine SSURGO's `slopegraddcp`; for slope itself, request a slope `renderingRule` or compute from neighbouring samples.

### Graceful degradation (when a host is blocked)

If preflight (or a live call) shows a needed host unreachable, do **not** guess or dead-end. Emit:
1. one line on which capability is degraded and why (host blocked),
2. the **exact parameterized query URL** for the user to open in a browser, and
3. an offer to **ingest the pasted result** — `geo.to_aoi_wkt()` takes a pasted GeoJSON/WKT blob directly, and the context-layer templates accept pasted `features` JSON.

This keeps the fallback consistent instead of improvising per question.

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
