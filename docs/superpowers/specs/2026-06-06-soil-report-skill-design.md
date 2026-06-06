# soil-report Skill — Design

**Date:** 2026-06-06
**Status:** Approved
**Project:** soil-skills — lightweight, installable Claude skills for live SSURGO querying

## Problem

Querying SSURGO today means R + soilDB, GIS tooling, or hand-rolling SOAP/REST calls against Soil Data Access. There is no lightweight way to ask "what's the soil at this address, and what works on it?" from an AI agent. This skill makes live SSURGO querying a zero-install capability: markdown instructions plus public, keyless HTTP APIs.

## Audience

AI-curious technical people — climate tech professionals and AI nerds interested in soils. Technically savvy, not necessarily soil-literate. They will read the skill source, so the skill itself is part of the product: "soil science as a prompt."

## Scope (v1)

One skill: **soil-report**. Input: a US street address, place name, or lat/lon, optionally with a specific question ("septic?", "vineyard?"). Output: a readable markdown soil report assembled from live SSURGO data.

Out of scope for v1: polygon/AOI queries, comparisons between locations, raw-SQL companion skill, non-US data, offline/bundled data. These are future siblings in the same repo.

## Architecture: pure SKILL.md + curl

The skill is markdown only — no scripts, no binaries, no dependencies beyond `curl`. It teaches Claude two keyless public APIs and ships tested fill-in-the-blank SQL templates. Claude substitutes coordinates/mukeys into templates; it never composes T-SQL from scratch for the core flow.

Rejected alternatives:

- **Bundled thin scripts (bash/python):** deterministic and token-cheap, but adds maintenance, assumes jq/python, and is less portable across agent platforms.
- **Compiled CLI binary:** most robust, but per-platform builds, release pipeline, and trust friction — the opposite of the lightweight goal.

## Data flow

1. **Geocode (only for addresses)** — Census Bureau Geocoder, free, keyless, US-only (SSURGO is US-only):
   `GET https://geocoding.geo.census.gov/geocoder/locations/onelineaddress?address=<oneline>&benchmark=Public_AR_Current&format=json`
   For well-known place names Claude may supply approximate coordinates itself and must say so. Raw lat/lon input skips this step.

2. **Point → mukey** — Soil Data Access tabular endpoint:
   `POST https://sdmdataaccess.sc.egov.usda.gov/Tabular/post.rest`
   body `{"query": "SELECT * FROM SDA_Get_Mukey_from_intersection_with_WktWgs84('POINT(<lon> <lat>)')", "format": "JSON+COLUMNNAME"}`

3. **Mukey → report data** — three templated T-SQL queries against the same endpoint:
   - **Overview:** `mapunit` + `muaggatt` — map unit name, drainage class, water table depth, flooding/ponding frequency, hydric %, farmland class.
   - **Components & horizons:** `component` + `chorizon` + `chtexturegrp` — series name, taxonomy, component %, horizon depths, texture, pH, organic matter, AWC, Ksat, depth to restrictive layer. Limited to components with `comppct_r >= 10`.
   - **Interpretations & ratings:** `cointerp` filtered to a curated rule-name list (septic tank absorption fields, dwellings with basements, local roads and streets, lawns/landscaping) plus NCCPI and land capability class from `component`.

## Report format

Sections, in order (if the user asked a specific question, lead with that answer and trim the rest):

1. **Location & map unit** — which SSURGO polygon, with the mandatory caveat that SSURGO is 1:24,000-scale mapping: "soils *mapped in this area*," not a point measurement.
2. **Your soil** — series name, taxonomy translated to plain English, profile by horizon.
3. **Key properties** — compact table: drainage, texture, pH, OM, AWC, Ksat, depth to restriction.
4. **What works here** — USDA cointerp ratings as plain verdicts.
5. **Farming** — prime farmland class, land capability, NCCPI.
6. **Hazards & water** — flooding, ponding, water table, hydric rating, hydrologic soil group.

Multi-component map units: report the dominant component in full; name the others with percentages.

## Hard rules (encoded in SKILL.md)

- Never fabricate values — every number traces to a query response.
- Always include the map-scale caveat.
- Report API failures honestly; never substitute invented soil data.

## Error handling

| Failure | Behavior |
|---|---|
| Geocoder can't resolve address | Ask user to clarify, or accept lat/lon |
| Point in water / urban NOTCOM / unmapped | Say so plainly; offer to check nearby |
| SDA down or slow | Report the failure honestly |
| Sparse/null property data | Show what exists; mark gaps as "not populated in SSURGO" |

## File structure

```
soil-skills/                      # repo (git)
├─ README.md
├─ skills/
│  └─ soil-report/
│     ├─ SKILL.md                 # ~150 lines: frontmatter, workflow, output spec, hard rules
│     └─ reference.md             # load-bearing: SQL templates, table docs, glossaries
└─ docs/superpowers/specs/        # design docs
```

**SKILL.md** — frontmatter `description` tuned to trigger on address/parcel/property + soil/septic/grow/build phrasing; the 4-step workflow; output format spec; hard rules.

**reference.md** — the four tested SQL templates with `{{mukey}}` / `{{lon lat}}` placeholders; a mini table-relationship doc (mapunit → component → chorizon; cointerp keys) enabling ad-hoc follow-up queries; glossaries (drainage classes, hydrologic soil groups A–D, land capability classes, interpretation rating classes, farmland class codes); the exact curated cointerp rule-name strings.

Distribution target: `npx skills add <owner>/soil-skills@soil-report`.

## Testing

Empirical, during development: every SQL template is run live via curl before it lands in reference.md, with real responses examined.

Validation matrix — each must yield a correct report or a graceful, honest miss:

| Case | Exercises |
|---|---|
| Davis, CA ag address | Prime farmland, alluvial series, full happy path |
| Floodplain/wetland site | Hydric rating, flooding/ponding, water table |
| Mountain site | Shallow restrictive layer, low capability class |
| Urban NOTCOM point | Graceful "not mapped" handling |
| Open water point | Graceful miss |
| Bogus address | Geocoder failure path |

## Success criteria

- A user with zero soil knowledge gets an accurate, readable report from one address, in one turn, with no installs.
- All six validation cases behave as specified.
- The skill installs cleanly via `npx skills add` and triggers on natural phrasings.
