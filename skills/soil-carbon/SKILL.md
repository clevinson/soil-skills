---
name: soil-carbon
description: Estimate soil carbon stock at any US location from live USDA SSURGO data — both organic (SOC) and inorganic (SIC, carbonates). Use when a user asks about soil carbon, carbon stock, carbon sequestration potential, or a carbon baseline at an address, parcel, farm, or coordinates — how many tonnes of carbon are in the soil.
---

# Soil Carbon

Estimate soil carbon stock (t C/ha) for any US location from live USDA data — **organic** (SOC) and **inorganic** (SIC, from carbonates) — computed transparently from horizon properties. Two keyless public HTTP APIs — `curl` (shell) or Python (sandbox). Zero installs.

**First, read `reference.md` in this skill's directory** — it has the tested templates (Q1, CQ), the HTTP specs with shell + Python examples, the network-access note, the SOC + SIC formulas, and worked examples.

These APIs are external; sandboxes (ChatGPT, claude.ai) block outbound internet by default. On a network error, see the "Network access required" note in reference.md.

## Workflow

1. **Get coordinates.** Lat/lon → use directly. Address → Census geocoder. No match → ask for a cross-street or coordinates.
2. **Point → map unit:** template Q1. ⚠️ `POINT(lon lat)` — longitude first. Empty `{}` → outside SSURGO coverage: say so.
3. **Pull carbon inputs:** template CQ → per-horizon organic matter, **carbonate (caco3_r)**, bulk density, and coarse fragments for components ≥ 10%.
4. **Compute both pools** for the dominant component using the method in reference.md, per horizon × `bulk density × thickness × (1 − frag/100)`, summed to **0–30 cm** and **0–100 cm** (clip the deepest horizon to the target depth):
   - **SOC** = `(om_r / 1.724)` ×  …
   - **SIC** = `(caco3_r × 0.12)` × …  (carbonate is 12% C by mass)
   - **Total** = SOC + SIC.
5. **Write the report.**

## Report format

**🌍 Soil carbon estimate** — lead with the headline at **0–30 cm** and **0–100 cm** in t C/ha (0–30 cm is the standard/IPCC depth), for the dominant soil (series + % of map unit): give **SOC, SIC, and total** separately. If SIC is non-trivial (calcareous soils), call that out — it's often missed. If other components ≥ 10% exist, name them and note their carbon may differ.

**🧮 How it's computed** — a per-horizon table: depth · OM% · OC% · CaCO₃% · bulk density · coarse-frag % · SOC · SIC (t C/ha). Then the one-line formulas so the math is auditable.

**📍 Context** — the map unit name and the SSURGO map-scale caveat. Optionally express the total as CO₂-equivalent (× 3.67) if the user cares about climate accounting — but see the rule below on not conflating the two pools.

**⚠️ What this is and isn't** — always: a **modeled baseline from representative survey values**, not a field measurement. **SOC ≠ SIC in behavior:** organic carbon is biologically active and management-sensitive; inorganic (carbonate) carbon is a large, slow, millennial-scale pool whose formation is not straightforwardly a climate sink — present them separately and don't imply SIC is readily sequesterable. For measured carbon, point to lab sampling or KSSL data.

If a horizon has null bulk density (or null OM / CaCO₃ for a pool), exclude it and say which — the total then covers only the horizons with data.

## Hard rules

- **Never fabricate a value.** Every number traces to a CQ response or the documented formula applied to it. Null inputs → flag and exclude, never guess (null `caco3_r` = no inorganic carbon).
- **Always show the method and the "estimate, not measurement" caveat**, and **keep SOC and SIC distinct** — that distinction is the integrity core of a soil-carbon number.
- **API failure → report it honestly.** A network error usually means blocked sandbox internet (see reference.md). Never substitute remembered carbon figures for live data.
- Show t C/ha (= Mg C/ha); add conversions (kg C/m², CO₂-eq) where they help.
