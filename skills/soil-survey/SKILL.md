---
name: soil-survey
description: Look up the USDA soil survey (SSURGO) for any US location and generate a readable soil report. Use when a user asks about the soil at an address, property, parcel, farm, or coordinates — what soil is there, or whether it suits septic systems, building, gardening, farming, vineyards, or other land uses. Also handles area/parcel summaries (a pasted WKT or GeoJSON polygon, or a radius), comparing soils across multiple locations, and looking up a soil series by name.
---

# Soil Survey

Readable soil report for any US location from live USDA data. Two keyless public HTTP APIs — call them with `curl` (shell) or Python (sandbox), whichever your runtime has. Zero installs.

**First, read `reference.md` in this skill's directory** — it has the tested SQL templates (Q1–Q4, D, AQ, SQ), the HTTP specs with shell + Python examples, the **host roster + preflight**, the **geometry helpers (`geo.py`)**, the **parcel + context-layer ArcGIS templates** (PQ, HQ, WQ, FQ, NW, EQ), table docs, and glossaries. Use a tested template when one fits; do not compose SDA SQL or ArcGIS queries from scratch.

These services are external; sandboxes (ChatGPT, claude.ai) block outbound internet by default. **Run the preflight** (reference.md) before building the workflow so you know which capabilities will run vs. degrade — don't discover blocks one dataset at a time. Allowlist by capability (host roster in reference.md), then retry in a fresh conversation. If a host is blocked, follow "Graceful degradation" (offer the parameterized URL + ingest the pasted result); never fabricate.

## Modes

Pick based on what the user asked; all share the same plumbing (see reference.md):

- **Point report** — soil at a single address/coordinate. The workflow below. Offer the WSS pin link `geo.wss_marker_url(lon, lat)` as the point-mode companion.
- **Area / parcel** — soils across a parcel/area. **Get the boundary programmatically:** a pasted WKT/GeoJSON/zipped-shapefile → `geo.to_aoi_wkt`; an address/parcel-ID → template **PQ** (address-field query is the *authoritative* selector — not spatial point-in-poly — then **sanity-gate the returned polygon** with `geo.approx_acres` + ring count); else a radius circle around the geocoded point. Run **AQ** (acreage + `clipped_wkt` per unit), then Q2/Q3/Q4 on the dominant unit(s). Lead with the dominant-units table, and **emit the map + shapefile/GeoJSON + the WSS deep link (`geo.wss_aoicoords_url`) by default** (reference.md "Area-mode outputs").
- **Compare** — two or more locations. Run the point workflow for each, then a side-by-side table + a short narrative diff.
- **Series lookup** — the user names a soil series, not a place. Use template **SQ** (taxonomy + extent) plus a representative profile, and link the OSD / SoilWeb. No geocoding.

### Point vs. parcel — decide scale first (don't silently default)

An address is genuinely ambiguous between "soil at this spot" and "soil across my property," and silently picking point can answer the wrong question. Lean from phrasing; ask only on real ambiguity (always-asking reads as not listening):

- **Lean point** — spot intent: "what soil type is at X", "will a septic system work at X", "pH at my address". A parcel would just add noise.
- **Lean parcel/area** — possessive or coverage language: "my property", "the lot", "soils *on* X", "how much of X is wet", "farmland classification of X", "all map units within the property line".
- **Ask** — bare address + generic verb ("give me the soil info at X", "tell me about the soil at X"): a one-tap choice (point vs. whole parcel) costs ~nothing and prevents a wrong-scale answer. Use the elicitation UI (single select, two options). Extra signal: if the geocoded point cheaply shows it sits in an implausibly large or attribute-null parcel (see PQ sanity gate), the bare point is unreliable — prefer the parcel path once you ask.
  - *Worked example:* "overview of the soil info (and maybe a basic map of the map units) at 20 Taunton Hill Rd" → ambiguous ("overview"+"map of map units" leans area but not decisively) → **ask**. Follow-up "full parcel boundary … all map units within the property line" → explicit parcel mode.

**Context layers** (any mode): soil + water are inseparable. For "is there a creek / wetland / flood risk," use the tested national ArcGIS templates — **HQ** (NHD streams/ponds), **WQ** (HUC12 watershed), **FQ** (FEMA flood zones), **EQ** (3DEP elevation), **NW** (NWI wetlands — probe order in reference.md). Cross-check, don't replace, the soil signals.

## Workflow

1. **Decide scale, then resolve location.** Infer point vs. parcel/area from the request (see "Point vs. parcel"); if genuinely ambiguous, ask the one-tap choice first.
   - **Point mode** → get coordinates: lat/lon given → use directly; street address → Census geocoder (no match → say so, ask for a cross-street/coords); well-known place name → approximate coords from your knowledge, disclosed.
   - **Parcel mode** → fetch the boundary with **PQ**: inspect the parcel layer's schema, query its **address field** (authoritative — not point-in-poly), **sanity-gate** the returned polygon (`geo.approx_acres` + ring count; a residential lot >1,000 ac or >10 rings, or null owner/address, is the wrong enclosing feature → fall back to the address query), then `geo.to_aoi_wkt`.
2. **Point → map unit:** template Q1. ⚠️ WKT order is `POINT(lon lat)` — longitude first. Empty `{}` response → outside SSURGO coverage (open water or unmapped): say so and offer to try a nearby point. (Parcel mode uses AQ instead — see Modes.)
3. **Pull data:** templates Q2 (overview), Q3 (components + horizons), Q3b (restrictions), Q4 (interpretations) with the mukey. They are independent — run all four in parallel.
4. **Write the report.**

## Report format

If the user asked a specific question ("will a septic system work?"), lead with that answer, then include only supporting sections. Otherwise, all sections:

**🗺️ Location & map unit** — matched address/coordinates, map unit name + symbol. ALWAYS include: SSURGO is 1:24,000-scale survey mapping — this describes soils *mapped in this area*, not a measurement at this exact point.

**🌱 Your soil** — dominant component: series name, taxonomy translated to plain English (what the soil *is* and how it formed), horizon-by-horizon profile with depths and textures. Name other components ≥ 10% with their percentages — they may behave very differently.

**📊 Key properties** — table for the dominant component: drainage class · surface texture · pH · organic matter % · AWC · Ksat · depth to restrictive layer (or "none within 2 m").

**🏠 What works here** — each Q4 interpretation as a plain verdict with the official rating in parentheses, e.g. "Septic: poor fit (Very limited)". "Very limited" means costly mitigation, not impossible. When the user cares about one rating, find what drives it (`ruledepth > 0` rows) and explain.

**🚜 Farming** — farmland classification · land capability class with meaning (1 best → 8, subclass letter = the limitation) · NCCPI in context (0–1, higher = more inherently productive).

**💧 Hazards & water** — flooding & ponding frequency · min water table depth (null = none within 2 m) · hydric % · hydrologic soil group with one-line meaning. **Cross-check the soil-derived signals against the independent layers when reachable:** SSURGO `flodfreqdcd` vs FEMA NFHL (FQ), and hydric % vs actual NHD streams/ponds (HQ) and NWI wetlands (NW). The HQ template answers "is there a creek/pond on the parcel" directly — prefer it over inferring from hydric soils alone.

For non-soil map units (Water, Urban land, NOTCOM, Pits): report what the map unit is, explain why there is no soil interpretation, offer to check a nearby point.

## Hard rules

- **Never fabricate a value.** Every number traces to a query response in this conversation. Null field → "not populated", not a guess. This extends to the new layers: don't call a stream perennial without its NHD FCode, or assert a flood zone the FEMA query didn't return.
- **Always include the map-scale / source caveat** — 1:24,000 for SSURGO, and the analogous caveat for each added layer: NHD ~1:24,000 (small channels may be absent), FEMA FIRM effective-date, parcel-data currency/precision (cadastral, not a survey).
- **National first, local last.** Primary endpoints must have nationwide coverage; state/county parcel services appear only as documented fallback tiers, and the report should **state which tier answered**.
- **Use `geo.py` for all geometry** (GeoJSON↔WKT, ring/orientation repair, `approx_acres` pre-check) — don't re-implement inline; lon/lat-swap and ring errors fail silently.
- **API/host failure → report it honestly** (SDA has bad days; use a ~60s timeout). A connection error usually means a blocked host — run the preflight first, and on a block use "Graceful degradation" (parameterized URL + ingest pasted result). Never substitute remembered facts for live data.
- Show original SSURGO units (cm, µm/s, cm/cm); add friendly conversions in parentheses where it helps.
- Questions beyond the templates (vineyards, solar, compaction...): run discovery template D — survey areas carry state-specific interpretations — then query the exact rule name it returns.
