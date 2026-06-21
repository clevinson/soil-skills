# soil-skills

Live USDA soil data as Claude skills. Ask about the soil at any US address — its properties, what it's suited for, how much carbon it holds — and get answers from the official survey, with every number traceable to a live query. No R, no GIS install, no API keys.

## What's here

Two skills, both pure markdown that teach an agent to query public US-government services directly (USDA Soil Data Access, the Census geocoder, and national USGS/FEMA/USFWS map layers).

### soil-survey — a soil report for any US location

From the USDA Soil Survey (SSURGO):

- **Soil & properties:** series and taxonomy in plain English, horizon-by-horizon profile, drainage, pH, texture, available water, restrictive layers.
- **Land-use ratings:** USDA's own verdicts for septic systems, dwellings, roads, and lawns; prime-farmland class; crop productivity (NCCPI).
- **Hazards & water:** flooding, water table, hydric soils, and runoff group, cross-checked against live FEMA flood zones and USGS streams.
- **Parcel / area:** look up a parcel boundary from its address (or take a pasted polygon or a radius), report area-weighted soils across it, and return a map, a shapefile/GeoJSON, and a Web Soil Survey deep link.
- **More:** compare two locations, look up a soil series by name, and pull nearby context — streams (NHD), watershed (HUC12), wetlands (NWI), elevation (3DEP).

```
> what's the soil at 1024 Olive Dr, Davis CA, and could it support a vineyard?
> map the soil units across the parcel at 20 Taunton Hill Rd, Newtown CT
```

### soil-carbon — soil carbon stock, honestly

Estimates organic (SOC) and inorganic (SIC) carbon in tonnes C/ha to 30 cm and 1 m, computed from horizon data with the method shown and an uncertainty band taken from the survey's own low/high range. Works for a single point or a whole parcel (area-weighted mean and total tonnes). Where a map unit is a mix of dissimilar soils, it reports a per-component range instead of a misleading single number.

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

> **Network access:** these query external services. Sandboxed runtimes (ChatGPT, claude.ai) block outbound internet by default — allowlist `geocoding.geo.census.gov` and `sdmdataaccess.sc.egov.usda.gov` for the core, plus the national-map hosts (`hydro.nationalmap.gov`, `hazards.fema.gov`, …) for the context layers, then start a fresh conversation. Claude Code's shell is generally open.

## How it works

Pure markdown, with one small geometry helper — no bundled binaries. At runtime the agent geocodes the location, finds its SSURGO map unit, and pulls map-unit, component, horizon, and interpretation data with pre-tested SQL templates, adding context layers (flood, streams, parcels) only as a question needs them. Every value in a report traces to a live query response; soil-carbon also shows the formula applied to those values. The skill files themselves document the templates, so the tool *is* the documentation.

## License & data

Code in this repo is licensed under the [MIT License](LICENSE).

The soil data itself is **not** covered by that license and isn't redistributed here — it's queried live from US federal government sources, which are in the **public domain** (17 U.S.C. § 105):

- Soil: USDA Natural Resources Conservation Service, Soil Survey Geographic Database (SSURGO), via [Soil Data Access](https://sdmdataaccess.sc.egov.usda.gov/).
- Geocoding: US Census Bureau [Geocoding Services](https://geocoding.geo.census.gov/).
- Context layers: USGS [The National Map](https://www.usgs.gov/programs/national-geospatial-program/national-map) (NHD, WBD, 3DEP), FEMA [NFHL](https://www.fema.gov/flood-maps), USFWS [National Wetlands Inventory](https://www.fws.gov/program/national-wetlands-inventory).

USDA requests that SSURGO data be cited when used; please keep the attribution above if you build on this.
