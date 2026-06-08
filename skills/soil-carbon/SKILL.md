---
name: soil-carbon
description: Estimate soil organic carbon (SOC) stock at any US location from live USDA SSURGO data. Use when a user asks about soil carbon, carbon stock, carbon sequestration potential, or a carbon baseline at an address, parcel, farm, or coordinates — how many tonnes of carbon are in the soil.
---

# Soil Carbon

Estimate soil organic carbon stock (t C/ha) for any US location from live USDA data, computed transparently from horizon properties. Two keyless public HTTP APIs — `curl` (shell) or Python (sandbox). Zero installs.

**First, read `reference.md` in this skill's directory** — it has the tested templates (Q1, CQ), the HTTP specs with shell + Python examples, the network-access note, the SOC formula, and a worked example.

These APIs are external; sandboxes (ChatGPT, claude.ai) block outbound internet by default. On a network error, see the "Network access required" note in reference.md.

## Workflow

1. **Get coordinates.** Lat/lon → use directly. Address → Census geocoder. No match → ask for a cross-street or coordinates.
2. **Point → map unit:** template Q1. ⚠️ `POINT(lon lat)` — longitude first. Empty `{}` → outside SSURGO coverage: say so.
3. **Pull carbon inputs:** template CQ → per-horizon OM, bulk density, and coarse fragments for components ≥ 10%.
4. **Compute SOC** for the dominant component using the method in reference.md: `OC% = om_r/1.724`, then per horizon `OC% × bulk density × thickness × (1 − frag/100)`, summed to **0–30 cm** and **0–100 cm** (clip the deepest horizon to the target depth).
5. **Write the report.**

## Report format

**🌍 Soil carbon estimate** — lead with the headline: SOC stock at **0–30 cm** and **0–100 cm** in t C/ha (mention 0–30 cm is the standard/IPCC reporting depth), for the dominant soil (series name + % of map unit). If other components ≥ 10% exist, name them and note their carbon may differ.

**🧮 How it's computed** — a per-horizon table: depth · OM% · OC% · bulk density · coarse-frag % · horizon stock (t C/ha). Then the one-line formula so the math is auditable.

**📍 Context** — the map unit name and the SSURGO map-scale caveat. Optionally express the 0–100 cm figure as CO₂-equivalent (× 3.67) if the user cares about climate accounting.

**⚠️ What this is and isn't** — always: this is a **modeled baseline from representative survey values**, not a field measurement; real SOC shifts with management, tillage, and recent land-use change. For measured carbon, point to lab sampling or KSSL data.

If a horizon has null OM or bulk density, exclude it and say which — the total then covers only the horizons with data.

## Hard rules

- **Never fabricate a value.** Every number traces to a CQ response or the documented formula applied to it. Null inputs → flag and exclude, never guess.
- **Always show the method and the "estimate, not measurement" caveat.** This is the integrity core of a carbon number.
- **API failure → report it honestly.** A network error usually means blocked sandbox internet (see reference.md). Never substitute remembered carbon figures for live data.
- Show t C/ha (= Mg C/ha); add conversions (kg C/m², CO₂-eq) where they help.
