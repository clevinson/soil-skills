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
