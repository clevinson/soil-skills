# soil-skills

Lightweight Claude skills for live [SSURGO](https://www.nrcs.usda.gov/resources/data-and-reports/soil-survey-geographic-database-ssurgo) soil data. No R, no soilDB, no installs — just markdown that teaches your agent two keyless public APIs.

## Skills

### soil-survey

Give it a US address (or coordinates) and get a readable soil report: what soil is there, its profile and properties, what USDA says works on it (septic, building, lawns), farmland ratings, and water/flooding hazards — all queried live from the USDA soil survey (SSURGO) via Soil Data Access.

```
> what's the soil like at 1024 Olive Dr, Davis CA? could it support a vineyard?
```

**Install — as a Claude Code plugin:**

```
/plugin marketplace add clevinson/soil-skills
/plugin install soil-survey@soil-skills
```

Then ask in plain language ("what's the soil at 1024 Olive Dr, Davis CA?") or invoke explicitly with `/soil-survey:soil-survey <address>`.

**Install — via the skills CLI** (works across Claude Code, ChatGPT, Codex, and other agents that support the [Agent Skills](https://github.com/anthropics/skills) standard):

```bash
npx skills add clevinson/soil-skills@soil-survey
```

> **Network access:** these are external APIs. Sandboxed runtimes (ChatGPT, claude.ai) block outbound internet by default — allowlist `geocoding.geo.census.gov` and `sdmdataaccess.sc.egov.usda.gov`, then start a fresh conversation. Claude Code's shell is generally open.

## How it works

The skill is pure markdown. At runtime the agent:

1. Geocodes the address (Census Bureau geocoder, keyless)
2. Finds the SSURGO map unit for the point (USDA Soil Data Access, T-SQL over HTTPS)
3. Pulls map unit, component, horizon, and interpretation data with pre-tested SQL templates
4. Writes the report — every number traceable to a live query response

## License & data

Code in this repo is licensed under the [MIT License](LICENSE).

The soil data itself is **not** covered by that license and isn't redistributed here — it's queried live from US federal government sources, which are in the **public domain** (17 U.S.C. § 105):

- Soil data: USDA Natural Resources Conservation Service, Soil Survey Geographic Database (SSURGO), via [Soil Data Access](https://sdmdataaccess.sc.egov.usda.gov/).
- Geocoding: US Census Bureau [Geocoding Services](https://geocoding.geo.census.gov/).

USDA requests that SSURGO data be cited when used; please keep the attribution above if you build on this.
