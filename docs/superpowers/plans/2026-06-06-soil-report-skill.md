# soil-report Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `soil-report` Claude skill — pure markdown, zero-install, address → live SSURGO soil report.

**Architecture:** Two markdown files (`SKILL.md` workflow + `reference.md` tested SQL templates) that teach Claude two keyless public APIs: the Census Bureau geocoder (address → lat/lon) and USDA Soil Data Access (T-SQL over HTTPS POST). No scripts, no binaries. All SQL templates below were verified live against SDA on 2026-06-06 (mukey 459259, Reiff very fine sandy loam, Davis CA).

**Tech Stack:** Markdown, `curl`, Census Geocoder API, USDA Soil Data Access (SDA) Tabular REST API.

**Spec:** `docs/superpowers/specs/2026-06-06-soil-report-skill-design.md`

---

## File structure

```
soil-skills/
├─ README.md                      # Task 3 — repo intro, install instructions
├─ skills/
│  └─ soil-report/
│     ├─ SKILL.md                 # Task 2 — frontmatter, workflow, report format, hard rules
│     └─ reference.md             # Task 1 — curl scaffold, SQL templates, table docs, glossaries
└─ docs/superpowers/
   ├─ specs/                      # exists
   └─ plans/                      # this file
```

`reference.md` comes first: it is the load-bearing file and SKILL.md refers to its template names (Q1, Q2, Q3, Q3b, Q4, D).

**Testing model:** this is a prompt artifact, not code — TDD translates to (a) every SQL template verified live before commit (done during planning; re-verified in Task 1), and (b) a six-case validation matrix run end-to-end in Task 4, exercising the happy path and every error path.

---

### Task 1: Create `reference.md`

**Files:**
- Create: `skills/soil-report/reference.md`

- [ ] **Step 1: Write the file with exactly this content**

````markdown
# SSURGO Query Reference

Everything here runs with `curl` against two keyless public APIs. All SQL templates were tested live against SDA (2026-06-06).

## APIs

### Census Geocoder (address → coordinates)

```bash
curl -s "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress?address={{URL_ENCODED_ADDRESS}}&benchmark=Public_AR_Current&format=json"
```

- Free, no key. **US addresses only** (fine — SSURGO is US-only).
- Success: `result.addressMatches[0].coordinates` → `x` = longitude, `y` = latitude; `matchedAddress` shows what was actually matched.
- Miss: `addressMatches` is `[]`. Common for campus buildings, PO boxes, new construction. Ask the user for a cross-street, city, or coordinates.

### Soil Data Access — SDA (all soil queries)

```bash
curl -s -X POST "https://sdmdataaccess.sc.egov.usda.gov/Tabular/post.rest" \
  -H "Content-Type: application/json" \
  -d '{"query":"{{SQL_ON_ONE_LINE}}","format":"JSON+COLUMNNAME"}'
```

- Accepts T-SQL (SQL Server dialect). No key, no auth.
- Response: `{"Table": [[column names], [row1...], [row2...]]}` — first array is headers.
- **No rows → response is `{}`** (empty object, not an empty Table).
- Escape single quotes inside SQL by doubling (`''`). Keep SQL on one line in the JSON body.
- It is a government SQL Server: occasionally slow or down. Add `--max-time 60`; on failure, report honestly and offer to retry.

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
````

- [ ] **Step 2: Re-verify two templates against the live API**

Run (Q1):
```bash
curl -s -X POST "https://sdmdataaccess.sc.egov.usda.gov/Tabular/post.rest" -H "Content-Type: application/json" -d '{"query":"SELECT * FROM SDA_Get_Mukey_from_intersection_with_WktWgs84('\''POINT(-121.7382 38.5410)'\'')","format":"JSON+COLUMNNAME"}'
```
Expected: `{"Table":[["mukey"],["459259"]]}`

Run (Q4, substituting mukey 459259):
```bash
curl -s -X POST "https://sdmdataaccess.sc.egov.usda.gov/Tabular/post.rest" -H "Content-Type: application/json" -d '{"query":"SELECT c.compname, c.comppct_r, ci.mrulename, ci.interphrc, ci.interphr FROM component c JOIN cointerp ci ON c.cokey = ci.cokey WHERE c.mukey = 459259 AND c.comppct_r >= 10 AND ci.ruledepth = 0 AND ci.mrulename IN ('\''ENG - Septic Tank Absorption Fields'\'','\''ENG - Dwellings With Basements'\'','\''ENG - Dwellings W/O Basements'\'','\''ENG - Local Roads and Streets'\'','\''ENG - Lawn, Landscape, Golf Fairway'\'','\''ENG - Shallow Excavations'\'','\''NCCPI - National Commodity Crop Productivity Index (Ver 3.0)'\'') ORDER BY c.comppct_r DESC, ci.mrulename","format":"JSON+COLUMNNAME"}'
```
Expected: 7 data rows for compname "Reiff" including `["Reiff","85","ENG - Septic Tank Absorption Fields","Very limited","1"]`. If any rule name returns no row, fix the string in reference.md to match the live `mrulename` (check with template D).

- [ ] **Step 3: Commit**

```bash
git add skills/soil-report/reference.md
git commit -m "feat: add SSURGO query reference with live-tested SQL templates"
```

---

### Task 2: Create `SKILL.md`

**Files:**
- Create: `skills/soil-report/SKILL.md`

- [ ] **Step 1: Write the file with exactly this content**

````markdown
---
name: soil-report
description: Generate a soil report for any US location by querying live USDA SSURGO data. Use when a user asks about the soil at an address, property, parcel, farm, or coordinates — what soil is there, or whether it suits septic systems, building, gardening, farming, vineyards, or other land uses.
---

# Soil Report

Readable soil report for any US location from live USDA data. Two keyless public APIs via `curl`. Zero installs.

**First, read `reference.md` in this skill's directory** — it has the tested SQL templates (Q1, Q2, Q3, Q3b, Q4, D), the curl scaffolds, table docs for ad-hoc queries, and glossaries. Do not compose SDA SQL from scratch when a template fits.

## Workflow

1. **Get coordinates.**
   - Lat/lon given → use directly.
   - Street address → Census geocoder (scaffold in reference.md). No match → tell the user (campus buildings, PO boxes, and new construction often miss) and ask for a cross-street or coordinates.
   - Well-known place name → you may use approximate coordinates from your own knowledge, but disclose that in the report.
2. **Point → map unit:** template Q1. ⚠️ WKT order is `POINT(lon lat)` — longitude first. Empty `{}` response → outside SSURGO coverage (open water or unmapped): say so and offer to try a nearby point.
3. **Pull data:** templates Q2 (overview), Q3 (components + horizons), Q3b (restrictions), Q4 (interpretations) with the mukey. They are independent — run all four in parallel.
4. **Write the report.**

## Report format

If the user asked a specific question ("will a septic system work?"), lead with that answer, then include only supporting sections. Otherwise, all sections:

**🗺️ Location & map unit** — matched address/coordinates, map unit name + symbol. ALWAYS include: SSURGO is 1:24,000-scale survey mapping — this describes soils *mapped in this area*, not a measurement at this exact point.

**🌱 Your soil** — dominant component: series name, taxonomy translated to plain English (what the soil *is* and how it formed), horizon-by-horizon profile with depths and textures. Name other components ≥ 10% with their percentages — they may behave very differently.

**📊 Key properties** — table for the dominant component: drainage class · surface texture · pH · organic matter % · AWC · Ksat · depth to restrictive layer (or "none within 2 m").

**🏠 What works here** — each Q4 interpretation as a plain verdict with the official rating in parentheses, e.g. "Septic: poor fit (Very limited)". "Very limited" means costly mitigation, not impossible. When the user cares about one rating, find what drives it (`ruledepth > 0` rows) and explain.

**🚜 Farming** — farmland classification · land capability class with meaning (1 best → 8, subclass letter = the limitation) · NCCPI in context (0–1, higher = more inherently productive).

**💧 Hazards & water** — flooding & ponding frequency · min water table depth (null = none within 2 m) · hydric % · hydrologic soil group with one-line meaning.

For non-soil map units (Water, Urban land, NOTCOM, Pits): report what the map unit is, explain why there is no soil interpretation, offer to check a nearby point.

## Hard rules

- **Never fabricate a value.** Every number traces to a query response in this conversation. Null field → "not populated in SSURGO", not a guess.
- **Always include the map-scale caveat.**
- **API failure → report it honestly** (SDA has bad days; use `--max-time 60`). Offer to retry. Never substitute remembered soil facts for live data.
- Show original SSURGO units (cm, µm/s, cm/cm); add friendly conversions in parentheses where it helps.
- Questions beyond the templates (vineyards, solar, compaction...): run discovery template D — survey areas carry state-specific interpretations — then query the exact rule name it returns.
````

- [ ] **Step 2: Check frontmatter parses and structure is consistent**

Run:
```bash
head -5 skills/soil-report/SKILL.md
grep -o 'Q[0-9]b\?\|template D' skills/soil-report/SKILL.md | sort -u
```
Expected: frontmatter opens/closes with `---` and has `name:` + `description:`; template references are exactly Q1, Q2, Q3, Q3b, Q4, template D — all of which exist in reference.md.

- [ ] **Step 3: Commit**

```bash
git add skills/soil-report/SKILL.md
git commit -m "feat: add soil-report SKILL.md workflow and report format"
```

---

### Task 3: Create `README.md`

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write the file with exactly this content**

````markdown
# soil-skills

Lightweight Claude skills for live [SSURGO](https://www.nrcs.usda.gov/resources/data-and-reports/soil-survey-geographic-database-ssurgo) soil data. No R, no soilDB, no installs — just markdown that teaches your agent two keyless public APIs.

## Skills

### soil-report

Give it a US address (or coordinates) and get a readable soil report: what soil is there, its profile and properties, what USDA says works on it (septic, building, lawns), farmland ratings, and water/flooding hazards — all queried live from USDA Soil Data Access.

```
> what's the soil like at 1024 Olive Dr, Davis CA? could it support a vineyard?
```

**Install:**

```bash
npx skills add corylevinson/soil-skills@soil-report
```

## How it works

The skill is pure markdown. At runtime the agent:

1. Geocodes the address (Census Bureau geocoder, keyless)
2. Finds the SSURGO map unit for the point (USDA Soil Data Access, T-SQL over HTTPS)
3. Pulls map unit, component, horizon, and interpretation data with pre-tested SQL templates
4. Writes the report — every number traceable to a live query response

Data citation: USDA Natural Resources Conservation Service, Soil Survey Geographic Database (SSURGO), via [Soil Data Access](https://sdmdataaccess.sc.egov.usda.gov/).
````

Note: replace `corylevinson/soil-skills` with the actual GitHub owner/repo at publish time — verify with `gh repo view --json nameWithOwner` once the repo has a remote.

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add repo README with install instructions"
```

---

### Task 4: Run the validation matrix

**Files:**
- Modify (only if fixes needed): `skills/soil-report/reference.md`, `skills/soil-report/SKILL.md`

For each case: run the workflow exactly as SKILL.md prescribes (the executor plays the role of the skill). A case passes if it yields a correct report or the specified graceful miss. When actual behavior differs from reference.md's documentation (e.g., empty-result shape), fix the doc to match reality.

- [ ] **Step 1: Case 1 — Davis CA happy path**

Run the full chain for `1024 Olive Dr, Davis, CA`:
```bash
curl -s "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress?address=1024+Olive+Dr%2C+Davis%2C+CA&benchmark=Public_AR_Current&format=json"
```
Expected: match at lon `-121.7382`, lat `38.5410`. Then Q1 → mukey `459259`; Q2–Q4 → Reiff very fine sandy loam, 85% Reiff component, 2 horizons, "Prime farmland if irrigated", septic "Very limited". Draft the full report and check every number against the responses.

- [ ] **Step 2: Case 2 — floodplain/hydric site (Yolo Bypass)**

Run Q1 with `POINT(-121.59 38.53)`, then Q2/Q3/Q3b/Q4 with the returned mukey.
Expected: a mukey in the Yolo Bypass with flooding frequency ≠ "None" and/or hydric % > 0; hazards section reads correctly. If this point happens to return Water, nudge east/west by ~0.01° until a soil map unit returns, and record the coordinates used.

- [ ] **Step 3: Case 3 — mountain site, restrictive layer (Sierra Nevada near Truckee)**

Run Q1 with `POINT(-120.19 39.33)`, then the data templates.
Expected: shallow-ish soil; Q3b returns a `reskind` (bedrock/densic) with depth, or `brockdepmin` is non-null in Q2; capability class high number (6–8). Confirm the report renders "depth to restrictive layer" correctly.

- [ ] **Step 4: Case 4 — urban point (downtown San Francisco)**

Run Q1 with `POINT(-122.4194 37.7749)`, then Q2/Q3.
Expected: map unit named "Urban land..." (possibly a complex) or NOTCOM; little/no horizon data. Confirm the non-soil map unit path: report names the unit, explains why no interpretation, offers nearby check.

- [ ] **Step 5: Case 5 — open water (Lake Tahoe center)**

Run Q1 with `POINT(-120.04 39.09)`.
Expected: empty `{}` (no coverage) **or** a mukey whose muname is "Water". Either way the graceful-miss path triggers. If the actual empty-result shape differs from `{}` as documented, fix reference.md.

- [ ] **Step 6: Case 6 — bogus address**

```bash
curl -s "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress?address=123+Fake+St%2C+Nowhere%2C+ZZ&benchmark=Public_AR_Current&format=json"
```
Expected: `"addressMatches":[]` → geocoder-miss path: ask user to clarify, suggest coordinates.

- [ ] **Step 7: Apply any fixes found and commit**

```bash
git add skills/soil-report/
git commit -m "fix: adjust reference docs to match observed API behavior from validation matrix"
```
(Skip the commit if no fixes were needed — note that in the task report.)

---

### Task 5: Local install & trigger test

**Files:**
- None created (symlink + manual test); fixes go to `skills/soil-report/SKILL.md` if triggering fails.

- [ ] **Step 1: Symlink the skill into the user's personal skills directory**

```bash
ln -sfn /Users/cory/Code/soil-skills/skills/soil-report /Users/cory/.claude/skills/soil-report
ls -la /Users/cory/.claude/skills/soil-report/
```
Expected: symlink resolves; `SKILL.md` and `reference.md` listed.

- [ ] **Step 2: Ask the user to trigger-test in a fresh session**

This step needs a human: ask Cory to open a new Claude Code session and try, e.g., `what's the soil at 1024 Olive Dr, Davis CA?` and a phrasing-variant like `would a vineyard work at my place near Winters?` Confirm the skill triggers and the report follows the format. If it doesn't trigger, tune the frontmatter `description` (add the missed phrasing) and re-test.

- [ ] **Step 3: Final commit & wrap-up**

```bash
git add -A
git commit -m "feat: soil-report skill v1 complete"
git log --oneline
```
Expected: clean history from spec → reference → SKILL → README → validation fixes → v1.

---

## Self-review notes

- **Spec coverage:** geocoding ✓ (Task 1 API docs + Case 1/6), point→mukey ✓ (Q1), all four content types ✓ (Q2/Q3/Q3b/Q4), report format ✓ (Task 2), hard rules ✓ (Task 2), error handling ✓ (Cases 2–6 + API docs), file structure ✓, distribution ✓ (README; `npx skills add` path verified at publish), all six validation cases ✓ (Task 4).
- **Tested-SQL guarantee:** Q1, Q2, Q3, Q3b, Q4, D all returned expected data live on 2026-06-06 against mukey 459259 during planning; Task 1 Step 2 re-verifies two of them at execution time.
- **Known deferment:** the README install command's owner/repo is finalized when the repo gets a GitHub remote (flagged inline in Task 3).
