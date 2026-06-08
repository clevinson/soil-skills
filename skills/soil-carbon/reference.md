# Soil Carbon Query Reference

Estimates soil carbon stock from USDA SSURGO — **organic** (SOC, from organic matter) and **inorganic** (SIC, from carbonates) — computed transparently from horizon data. Two keyless public APIs; call them with `curl` (shell) or Python (sandbox). Tested live against SDA (2026-06-07).

## Network access required

External APIs. Skill sandboxes block outbound internet by default. If calls fail with a network error, the host's domain allowlist must include — or allow all domains:

- `geocoding.geo.census.gov`
- `sdmdataaccess.sc.egov.usda.gov`

On claude.ai / ChatGPT, enable network access, allowlist the two domains, then start a fresh conversation. Never fabricate carbon values if you cannot reach the APIs — say so.

## APIs

### Census Geocoder (address → coordinates)

**Request:** `GET https://geocoding.geo.census.gov/geocoder/locations/onelineaddress`
with query params `address={{URL_ENCODED_ADDRESS}}`, `benchmark=Public_AR_Current`, `format=json`

- Success: `result.addressMatches[0].coordinates` → `x` = longitude, `y` = latitude.
- Miss: `addressMatches` is `[]` → ask for a cross-street or coordinates.

*Shell:*
```bash
curl -s "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress?address={{URL_ENCODED_ADDRESS}}&benchmark=Public_AR_Current&format=json"
```
*Python:*
```python
import json, urllib.parse, urllib.request
params = urllib.parse.urlencode({"address": address, "benchmark": "Public_AR_Current", "format": "json"})
url = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress?" + params
resp = json.loads(urllib.request.urlopen(url, timeout=60).read())
matches = resp["result"]["addressMatches"]  # [] = no match
```

### Soil Data Access — SDA

**Request:** `POST https://sdmdataaccess.sc.egov.usda.gov/Tabular/post.rest`
- Header: `Content-Type: application/json`
- Body (JSON): `{"query": "<SQL>", "format": "JSON+COLUMNNAME"}`
- Response: `{"Table": [[column names], [row...]]}`; `{}` if no rows.

*Shell:* single-quoted JSON body, so double single-quotes inside SQL (`''`) and keep SQL on one line.
```bash
curl -s --max-time 60 -X POST "https://sdmdataaccess.sc.egov.usda.gov/Tabular/post.rest" \
  -H "Content-Type: application/json" \
  -d '{"query":"{{SQL_ON_ONE_LINE}}","format":"JSON+COLUMNNAME"}'
```
*Python:* pass a dict; `json.dumps` escapes; SQL may be multi-line.
```python
import json, urllib.request
url = "https://sdmdataaccess.sc.egov.usda.gov/Tabular/post.rest"
body = json.dumps({"query": sql, "format": "JSON+COLUMNNAME"}).encode()
req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
resp = json.loads(urllib.request.urlopen(req, timeout=60).read())
rows = resp.get("Table", [])
```

## Query templates

### Q1 — point → mukey

```sql
SELECT * FROM SDA_Get_Mukey_from_intersection_with_WktWgs84('POINT({{lon}} {{lat}})')
```

⚠️ WKT order is `POINT(lon lat)` — longitude first. Empty `{}` → outside SSURGO coverage (water/unmapped): say so.

### CQ — carbon inputs by horizon

Pulls everything the carbon computation needs — **organic** (`om_r`) and **inorganic** (`caco3_r`). Coarse-fragment volume is summed from the child `chfrags` table via a correlated subquery (joining `chfrags` directly would multiply horizon rows).

```sql
SELECT c.compname, c.comppct_r, c.majcompflag,
       ch.hzname, ch.hzdept_r, ch.hzdepb_r,
       ch.om_l, ch.om_r, ch.om_h,
       ch.caco3_l, ch.caco3_r, ch.caco3_h,
       ch.dbthirdbar_r,
       (SELECT SUM(cf.fragvol_r) FROM chfrags cf WHERE cf.chkey = ch.chkey) AS fragvol_r
FROM component c
JOIN chorizon ch ON c.cokey = ch.cokey
WHERE c.mukey = {{mukey}} AND c.comppct_r >= 10
ORDER BY c.comppct_r DESC, ch.hzdept_r
```

| Column | Meaning |
|---|---|
| `compname` / `comppct_r` | Soil series / % of map unit |
| `majcompflag` | "Yes" = major component |
| `hzdept_r`, `hzdepb_r` | Horizon top & bottom depth (cm) |
| `om_l` / `om_r` / `om_h` | Organic matter %, low / representative / high → organic carbon |
| `caco3_l` / `caco3_r` / `caco3_h` | Calcium carbonate equivalent %, low / rep / high → inorganic carbon (null = none) |
| `dbthirdbar_r` | Bulk density at ⅓ bar, g/cm³ (representative) |
| `fragvol_r` (summed) | Coarse fragment volume, % (null = none) |

`_l` / `_h` are SSURGO's stated low/high for the property across the component — used for the uncertainty band (see below). They are **not** a confidence interval.

## Carbon computation

Two pools — report both, plus their sum (total soil carbon). For each horizon of the dominant component (highest `comppct_r`), with thickness clipped to the target depth (e.g. for 0–100 cm, a 80–130 cm horizon contributes only 20 cm) and `(1 − fragvol/100)` removing coarse-fragment volume that holds no fine-earth carbon:

**Organic (SOC):**
1. Organic carbon: `OC% = om_r / 1.724` — the van Bemmelen factor (organic matter → organic carbon).
2. Horizon stock (t C/ha): `OC% × dbthirdbar_r × thickness_cm × (1 − fragvol/100)`.

**Inorganic (SIC):**
1. Carbonate carbon: `IC% = caco3_r × 0.1200` — CaCO₃ is 12.0% carbon by mass (12.01 / 100.09 g·mol⁻¹), assuming carbonate is calcite.
2. Horizon stock (t C/ha): `IC% × dbthirdbar_r × thickness_cm × (1 − fragvol/100)`.

Dimensional check (both): %(g C/100 g) × (g/cm³) × cm over 1 ha = Mg C/ha.

**Totals:** sum each pool over horizons to **0–30 cm** (IPCC / standard reporting depth) and **0–100 cm** (fuller profile). Total soil carbon = SOC + SIC. Report SOC, SIC, and total separately — they behave very differently (see caveats).

Skip horizons with null `dbthirdbar_r` (or, for a given pool, null `om_r` / `caco3_r`) and flag them — do not guess. Treat null `caco3_r` or `fragvol_r` as 0.

### Uncertainty band

Report each figure as `representative [low – high]`. Compute **low** by using `om_l` and `caco3_l` in place of the `_r` values, and **high** with `om_h` / `caco3_h` — holding bulk density and fragments at representative. Carbon-stock uncertainty is dominated by the organic-matter (and carbonate) concentration range; bulk density's range adds only a few percent and its `_l`/`_h` are not physically paired with the OM extremes (in SSURGO, `om_h` may sit with `dbthirdbar_h`, the opposite of real soils), so do not combine all-low/all-high — vary only the carbon concentration.

**State plainly what the band is and isn't.** It is the range implied by **SSURGO's own low/high organic-matter and carbonate estimates** for this map-unit component. It is **NOT** a statistical confidence interval (the L/H carry no stated probability), and it does **NOT** include the errors that often dominate:

- *which* component you actually have at this point (map units are composites; we used the dominant one — a minor component can differ greatly);
- map-delineation / positional uncertainty (whether the point is even in the right polygon);
- bulk-density and coarse-fragment uncertainty (held at representative here);
- temporal change, management, land-use history, and lab/pedon measurement error.

So **true uncertainty is wider than this band** — present it as "SSURGO's stated property range," never as a guarantee.

### Worked examples (tested live)

**Zamora loam, Davis CA (mukey 459310)** — non-calcareous, SIC ≈ 0:

| Horizon | Depth cm | OM% | OC% | CaCO₃% | BD | Frag% | SOC t C/ha |
|---|---|---|---|---|---|---|---|
| H1 | 0–25 | 3.0 | 1.74 | 0 | 1.48 | 0 | 64.4 |
| H2 | 25–102 | 0.75 | 0.435 | 0 | 1.40 | 0 | 45.7 (to 100 cm) |

→ 0–30 cm: **SOC 67 [45–90], SIC 0, total 67 [45–90]** · 0–100 cm: **SOC 110 [73–147], SIC 0, total 110 [73–147]** t C/ha. The ±33% band comes entirely from SSURGO's OM low/high (e.g. H1 om 2–4%).

**Harkey, near Las Cruces NM (mukey 634572)** — calcareous; SIC is ~40% of total:

| Horizon | Depth cm | OM% | CaCO₃% | BD | SOC | SIC |
|---|---|---|---|---|---|---|
| H1 | 0–30 | 0.9 | 3 | 1.50 | — | — |
| H2 | 30–152 | 0.9 | 3 | 1.45 | — | — |

→ 0–30 cm: **SOC 23.5, SIC 16.2, total 39.7** · 0–100 cm: **SOC 76.5, SIC 52.7, total 129.2** t C/ha.

### Python helper (optional)

```python
def carbon_stock(horizons, depth_limit_cm, om_key="om_r", caco3_key="caco3_r"):
    """horizons: dicts with hzdept_r, hzdepb_r, dbthirdbar_r, fragvol_r, and the om/caco3 keys.
    Returns (soc, sic, gaps) in tonnes C/ha. Pass om_l/caco3_l (or _h) for the band."""
    soc = sic = 0.0
    gaps = []
    for h in horizons:
        top, bot = h["hzdept_r"], h["hzdepb_r"]
        bd = h["dbthirdbar_r"]
        if top is None or bot is None or bd is None:
            if not (top is None or bot is None):
                gaps.append(h.get("hzname"))
            continue
        bot = min(bot, depth_limit_cm)
        if bot <= top:
            continue
        vol = bd * (bot - top) * (1 - (h["fragvol_r"] or 0.0) / 100.0)
        if h.get(om_key) is not None:
            soc += (h[om_key] / 1.724) * vol
        sic += ((h.get(caco3_key) or 0.0) * 0.12) * vol
    return soc, sic, gaps

# representative + band (bulk density held at rep — vary only the carbon concentration)
soc_r, sic_r, gaps = carbon_stock(horizons, 30)
soc_lo, sic_lo, _  = carbon_stock(horizons, 30, "om_l", "caco3_l")
soc_hi, sic_hi, _  = carbon_stock(horizons, 30, "om_h", "caco3_h")
```

## Caveats (always surface)

- SSURGO values are **representative/estimated**, not measured at this point. These are **modeled baselines**, not field measurements.
- The **uncertainty band is SSURGO's stated OM/carbonate range, not a confidence interval**, and excludes the component-choice, positional, bulk-density, and temporal errors that often dominate — true uncertainty is wider (see "Uncertainty band" above).
- **SOC and SIC are not interchangeable.** Organic carbon is biologically active and management-sensitive (tillage, cover crops, land-use change shift it on yearly–decadal scales). Inorganic carbon (pedogenic/lithogenic carbonate) is a large, slow pool that turns over on millennial timescales; whether its formation is a net climate sink or source depends on the cation and bicarbonate source, so do not present SIC as readily "sequesterable." Keep them separate.
- `caco3_r` is **calcium carbonate equivalent** — it does not distinguish pedogenic (formed in place) from inherited/lithogenic carbonate, and the ×0.12 factor assumes calcite (dolomite would differ slightly).
- SSURGO is 1:24,000-scale mapping: it describes soils **mapped in this area**, not this exact spot.
- For measured carbon you'd need lab data (KSSL) or on-site sampling — out of scope here.

## Units

OM/OC and CaCO₃/IC in % by weight · bulk density g/cm³ · depth cm · carbon stock t C/ha (= Mg C/ha). 1 t C/ha = 0.1 kg C/m². To CO₂-equivalent: × 3.67.
