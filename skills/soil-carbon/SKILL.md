---
name: soil-carbon
description: Estimate soil carbon stock at any US location from live USDA SSURGO data — both organic (SOC) and inorganic (SIC, carbonates). Use when a user asks about soil carbon, carbon stock, carbon sequestration potential, or a carbon baseline at an address, parcel, farm, or coordinates — how many tonnes of carbon are in the soil. Handles a single point or an area/parcel (a pasted WKT or GeoJSON polygon, or a radius) for area-weighted and total carbon.
---

# Soil Carbon

Estimate soil carbon stock (t C/ha) for any US location from live USDA data — **organic** (SOC) and **inorganic** (SIC, from carbonates) — computed transparently from horizon properties. Two keyless public HTTP APIs — `curl` (shell) or Python (sandbox). Zero installs.

**First, read `reference.md` in this skill's directory** — it has the tested templates (Q1, CQ), the HTTP specs with shell + Python examples, the network-access note, the SOC + SIC formulas, and worked examples.

These APIs are external; sandboxes (ChatGPT, claude.ai) block outbound internet by default. On a network error, see the "Network access required" note in reference.md.

## Modes

- **Point** (default) — carbon at a single address/coordinate. The workflow below. Honesty rule: only give a single number for a **consociation**; for a complex/association/undifferentiated map unit, show the components and a range (see Report format).
- **Area / parcel** — carbon across an AOI. If the user pastes a WKT or GeoJSON polygon, use it; otherwise build a radius circle around the geocoded point. Follow "Area mode" in reference.md: intersect the AOI to get map units + acres, compute each unit's **component-weighted** carbon, then report the **area-weighted mean** (`rep [low–high]`, t C/ha) **and the total tonnes** in the AOI, with a per-map-unit table. (Area mode blends components legitimately — it's areal integration, not a point.)

## Workflow (point mode)

1. **Get coordinates.** Lat/lon → use directly. Address → Census geocoder. No match → ask for a cross-street or coordinates.
2. **Point → map unit:** template Q1. ⚠️ `POINT(lon lat)` — longitude first. Empty `{}` → outside SSURGO coverage: say so.
3. **Pull carbon inputs:** template CQ → `mukind` plus per-horizon organic matter (`om_l/_r/_h`), **carbonate (`caco3_l/_r/_h`)**, bulk density, and coarse fragments for every component ≥ 10%.
4. **Compute each component's pools** using the method in reference.md, per horizon × `bulk density × thickness × (1 − frag/100)`, summed to **0–30 cm** and **0–100 cm** (clip the deepest horizon to the target depth):
   - **SOC** = `(om_r / 1.724)` ×  …
   - **SIC** = `(caco3_r × 0.12)` × …  (carbonate is 12% C by mass)
   - **Total** = SOC + SIC.
   - **Uncertainty band:** recompute low/high using `om_l/caco3_l` and `om_h/caco3_h` (bulk density held at representative). Report each figure as `rep [low–high]`.
5. **Decide what to report from `mukind`** (see reference.md "Reporting by map unit kind"): consociation → the dominant component as a single headline; complex/association/undifferentiated → all components + a range, no single value.
6. **Write the report.**

## Report format

**🌍 Soil carbon estimate** — depends on how many components ≥10% the map unit has (with `mukind` as the guide), at **0–30 cm** and **0–100 cm** in t C/ha (0–30 cm is the standard/IPCC depth):
- **Consociation, or any map unit with only one component ≥10%** → lead with a single headline for that soil (series + % of map unit): **SOC, SIC, and total**, each as **`rep [low–high]`**. If the kind is a complex/association that happens to resolve to one major soil, note the minor (<10%) components exist.
- **Complex / association / undifferentiated with ≥2 components ≥10%** → **do not give a single number.** State the kind ("this is a complex of N dissimilar soils — SSURGO doesn't resolve which is at your exact spot"), show a **components table** (component · % · SOC · SIC · total `[band]`), and give an honest **range** ("≈ X–Y t C/ha depending which soil you're on").
- **Non-soil** map unit (Urban land, Water) → there's no soil carbon to estimate; say so, don't report 0.

In all cases, if SIC is non-trivial (calcareous soils), call it out — it's often missed.

**🧮 How it's computed** — a per-horizon table (for the dominant / illustrative component): depth · OM% · OC% · CaCO₃% · bulk density · coarse-frag % · SOC · SIC (t C/ha). Then the one-line formulas so the math is auditable.

**📊 What the range means** — one or two sentences: the band is **SSURGO's own low/high organic-matter and carbonate estimates**, not a confidence interval. It excludes the errors that often dominate — which component you actually have, map/positional error, bulk-density and temporal change — so **real uncertainty is wider**. Don't let the band imply false precision.

**📍 Context** — the map unit name and the SSURGO map-scale caveat. Optionally express the total as CO₂-equivalent (× 3.67) if the user cares about climate accounting — but see the rule below on not conflating the two pools.

**⚠️ What this is and isn't** — always: a **modeled baseline from representative survey values**, not a field measurement. **SOC ≠ SIC in behavior:** organic carbon is biologically active and management-sensitive; inorganic (carbonate) carbon is a large, slow, millennial-scale pool whose formation is not straightforwardly a climate sink — present them separately and don't imply SIC is readily sequesterable. For measured carbon, point to lab sampling or KSSL data.

If a horizon has null bulk density (or null OM / CaCO₃ for a pool), exclude it and say which — the total then covers only the horizons with data.

## Hard rules

- **Never fabricate a value.** Every number traces to a CQ response or the documented formula applied to it. Null inputs → flag and exclude, never guess (null `caco3_r` = no inorganic carbon).
- **Always show the method and the "estimate, not measurement" caveat**, and **keep SOC and SIC distinct** — that distinction is the integrity core of a soil-carbon number.
- **The band is SSURGO's stated property range, not a confidence interval.** Never present it as "±X% certain" or a guarantee; say true uncertainty is wider.
- **No single point number when ≥2 components ≥10% in a non-consociation map unit.** Show the components and a range instead. A consociation — or any map unit that resolves to a single major component — gets one headline value. (Area mode is exempt — areal aggregation legitimately blends.)
- **API failure → report it honestly.** A network error usually means blocked sandbox internet (see reference.md). Never substitute remembered carbon figures for live data.
- Show t C/ha (= Mg C/ha); add conversions (kg C/m², CO₂-eq) where they help.
