# soil-skills v2 — Design (soil-carbon, area/compare/series)

**Date:** 2026-06-07
**Status:** Approved
**Builds on:** v1 soil-survey skill (`docs/superpowers/specs/2026-06-06-soil-report-skill-design.md`)

## Scope

Four additions, two deliverables:

1. **`soil-carbon`** — a NEW sibling skill: address → estimated soil organic carbon (SOC) stock.
2. **`soil-survey` upgrades** — three new modes folded into the existing skill:
   - **Area** — area-weighted soils across an AOI (pasted WKT/GeoJSON polygon, or a radius around the point).
   - **Compare** — run the report for 2+ locations, diff them.
   - **Series lookup** — query by soil series name instead of by location.

### Decisions

- **Area boundary:** no free national parcel-polygon API exists, so the skill's input surface is a **pasted WKT or GeoJSON polygon**, with a **radius around the geocoded point** as the no-polygon fallback. Future: out-of-band generation of county/block/parcel GeoJSON (handled elsewhere, fed in here).
- **soil-carbon is its own skill** (not a soil-survey mode) — best discoverability, strongest standalone climate story, and room to add other SOC sources (SoilGrids, etc.) later. Accepts a small amount of duplicated geocode/SDA scaffold to stay self-contained and portable.

## soil-carbon

### Data flow
Geocode (address) → Q1 point→mukey → one consolidated carbon query (CQ) → compute SOC → report.

CQ pulls, per horizon of each component ≥ 10%: `hzdept_r`, `hzdepb_r`, `om_r`, `dbthirdbar_r` (bulk density ⅓-bar), and coarse-fragment volume summed from the child `chfrags` table (correlated subquery to avoid row multiplication).

### SOC method (computed, transparent)
`valu1` (gSSURGO precomputed SOC) is NOT exposed via SDA, so we compute from horizons:

- Organic carbon: `OC% = om_r / 1.724` (van Bemmelen factor, OM→OC).
- Horizon thickness: `hzdepb_r − hzdept_r`, clipped to the target depth.
- Per-horizon stock: `SOC = OC% × dbthirdbar_r × thickness_cm × (1 − fragvol/100)` → tonnes C/ha (Mg/ha). (Dimensional check: OC%·BD(g/cm³)·thickness(cm) = Mg C/ha.)
- Sum horizons to **0–30 cm** (IPCC/standard reporting) and **0–100 cm** (fuller profile). Report both.
- Computed for the dominant component; other components ≥ 10% named with their percentages.

Validated live (mukey 459310, Zamora loam, Davis): 0–30 cm ≈ 67 t C/ha, 0–100 cm ≈ 110 t C/ha.

### Report
- Headline: SOC stock at 0–30 and 0–100 cm (t C/ha), for the dominant soil.
- Per-horizon table: depth, OM%, OC%, bulk density, coarse-frag %, horizon SOC.
- Method line (the formula) + the SSURGO map-scale caveat.
- Honesty: this is an **estimate from representative survey values**, not a measurement; real SOC varies with management and recent land use. Null `om_r`/`dbthirdbar_r` horizons are flagged and excluded, not guessed.

## soil-survey upgrades

### Area mode
Input: a WKT/GeoJSON polygon (preferred) or a radius around the point. Query: intersect `mupolygon` with the AOI, area-weight by intersected acreage per map unit.

Validated spatial pattern (geometry for intersection, cast to geography for area in acres):
```sql
SELECT mu.mukey, mu.muname,
  SUM(GEOGRAPHY::STGeomFromText(
        mp.mupolygongeo.STIntersection(GEOMETRY::STGeomFromText('<AOI_WKT>',4326)).STAsText(), 4326
      ).STArea() * 0.000247105) AS acres
FROM mupolygon mp JOIN mapunit mu ON mu.mukey = mp.mukey
WHERE mp.mupolygongeo.STIntersects(GEOMETRY::STGeomFromText('<AOI_WKT>',4326)) = 1
GROUP BY mu.mukey, mu.muname
ORDER BY acres DESC
```
GeoJSON input is converted to WKT before substitution. Geography requires valid ring orientation; if STArea throws on a self-intersecting AOI, report the issue rather than guessing. Output: dominant-units table (map unit, acres, % of AOI), then the standard per-unit detail for the top unit(s).

### Compare mode
Run the v1 report flow for each location; emit a side-by-side table of the key properties + interpretations, then a short narrative diff. No new SQL.

### Series lookup
Input: a series name. Query `component`/`chorizon` filtered on `compname = '<series>'` to summarize the series' representative profile and taxonomy (aggregate or representative instance), with a link to the Official Series Description (OSD). Clearly distinct from a location lookup.

## Packaging

Adding `skills/soil-carbon/` to the repo. The plugin auto-discovers all `skills/*`, so the plugin now bundles two skills — rename the plugin from `soil-survey` to an umbrella (`soil-skills`) so the name reflects the bundle. README + marketplace updated accordingly.

## Out of scope (v2)
SoilGrids/global SOC, KSSL lab data, real parcel fetching, visuals/maps, MCP server. All remain future siblings.
