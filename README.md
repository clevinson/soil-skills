# soil-skills

Lightweight Claude skills for live [SSURGO](https://www.nrcs.usda.gov/resources/data-and-reports/soil-survey-geographic-database-ssurgo) soil data. No R, no soilDB, no installs — just markdown that teaches your agent two keyless public APIs.

## Skills

### soil-survey

Give it a US address (or coordinates) and get a readable soil report: what soil is there, its profile and properties, what USDA says works on it (septic, building, lawns), farmland ratings, and water/flooding hazards — all queried live from the USDA soil survey (SSURGO) via Soil Data Access.

```
> what's the soil like at 1024 Olive Dr, Davis CA? could it support a vineyard?
```

**Install:**

```bash
npx skills add clevinson/soil-skills@soil-survey
```

## How it works

The skill is pure markdown. At runtime the agent:

1. Geocodes the address (Census Bureau geocoder, keyless)
2. Finds the SSURGO map unit for the point (USDA Soil Data Access, T-SQL over HTTPS)
3. Pulls map unit, component, horizon, and interpretation data with pre-tested SQL templates
4. Writes the report — every number traceable to a live query response

Data citation: USDA Natural Resources Conservation Service, Soil Survey Geographic Database (SSURGO), via [Soil Data Access](https://sdmdataaccess.sc.egov.usda.gov/).
