# soil-skills

Lightweight Claude skills for live [SSURGO](https://www.nrcs.usda.gov/resources/data-and-reports/soil-survey-geographic-database-ssurgo) soil data. No R, no soilDB, no installs — just markdown that teaches your agent two keyless public APIs.

## Skills

### soil-survey

Give it a US address (or coordinates) and get a readable soil report: what soil is there, its profile and properties, what USDA says works on it (septic, building, lawns), farmland ratings, and water/flooding hazards — all queried live from the USDA soil survey (SSURGO) via Soil Data Access.

```
> what's the soil like at 1024 Olive Dr, Davis CA? could it support a vineyard?
```

It also handles:
- **Area / parcel** — paste a WKT or GeoJSON polygon (or give a radius) for area-weighted soils across a parcel, not just one point.
- **Compare** — soils across two or more locations, side by side.
- **Series lookup** — "tell me about the Yolo series" (by name, no address).

### soil-carbon

Estimate **soil organic carbon (SOC) stock** at any US location — tonnes C/ha at 0–30 cm and 0–100 cm — computed transparently from SSURGO horizon data (organic matter, bulk density, thickness, coarse-fragment correction), with the method shown.

```
> how much carbon is in the soil at 1024 Olive Dr, Davis CA?
```

## Install

**As a Claude Code plugin** (gets both skills):

```
/plugin marketplace add clevinson/soil-skills
/plugin install soil@soil-skills
```

Then ask in plain language, or invoke explicitly: `/soil:soil-survey <address>` · `/soil:soil-carbon <address>`.

**Via the skills CLI** (works across Claude Code, ChatGPT, Codex, and other agents that support the [Agent Skills](https://github.com/anthropics/skills) standard):

```bash
npx skills add clevinson/soil-skills@soil-survey
npx skills add clevinson/soil-skills@soil-carbon
```

> **Network access:** these are external APIs. Sandboxed runtimes (ChatGPT, claude.ai) block outbound internet by default — allowlist `geocoding.geo.census.gov` and `sdmdataaccess.sc.egov.usda.gov`, then start a fresh conversation. Claude Code's shell is generally open.

## How it works

The skills are pure markdown. At runtime the agent:

1. Geocodes the address (Census Bureau geocoder, keyless)
2. Finds the SSURGO map unit for the point (USDA Soil Data Access, T-SQL over HTTPS)
3. Pulls map unit, component, horizon, and interpretation data with pre-tested SQL templates
4. Writes the report — every number traceable to a live query response (soil-carbon additionally shows the SOC formula applied to those values)

## License & data

Code in this repo is licensed under the [MIT License](LICENSE).

The soil data itself is **not** covered by that license and isn't redistributed here — it's queried live from US federal government sources, which are in the **public domain** (17 U.S.C. § 105):

- Soil data: USDA Natural Resources Conservation Service, Soil Survey Geographic Database (SSURGO), via [Soil Data Access](https://sdmdataaccess.sc.egov.usda.gov/).
- Geocoding: US Census Bureau [Geocoding Services](https://geocoding.geo.census.gov/).

USDA requests that SSURGO data be cited when used; please keep the attribution above if you build on this.
