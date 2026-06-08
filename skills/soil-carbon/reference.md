# Soil Carbon Query Reference

Estimates soil organic carbon (SOC) stock from USDA SSURGO, computed transparently from horizon data. Two keyless public APIs; call them with `curl` (shell) or Python (sandbox). Tested live against SDA (2026-06-07).

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

Pulls everything the SOC computation needs. Coarse-fragment volume is summed from the child `chfrags` table via a correlated subquery (joining `chfrags` directly would multiply horizon rows).

```sql
SELECT c.compname, c.comppct_r, c.majcompflag,
       ch.hzname, ch.hzdept_r, ch.hzdepb_r,
       ch.om_r, ch.dbthirdbar_r,
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
| `om_r` | Organic matter, % by weight (representative) |
| `dbthirdbar_r` | Bulk density at ⅓ bar, g/cm³ (representative) |
| `fragvol_r` (summed) | Coarse fragment volume, % (null = none) |

## SOC computation

For each horizon of the dominant component (highest `comppct_r`):

1. **Organic carbon:** `OC% = om_r / 1.724` — the van Bemmelen factor converting organic matter to organic carbon.
2. **Thickness:** `hzdepb_r − hzdept_r`, clipped so it does not extend past the target depth (e.g. for 0–100 cm, a 80–130 cm horizon contributes only 20 cm).
3. **Horizon stock (t C/ha):** `OC% × dbthirdbar_r × thickness_cm × (1 − fragvol/100)`.
   Dimensional check: %(g C/100 g) × (g/cm³) × cm over 1 ha = Mg C/ha. Coarse fragments hold no carbon, so the `(1 − fragvol/100)` term removes their volume.
4. **Total:** sum horizon stocks to **0–30 cm** (IPCC / standard reporting depth) and **0–100 cm** (fuller profile). Report both.

Skip horizons with null `om_r` or `dbthirdbar_r` and flag them — do not guess. Treat null `fragvol_r` as 0.

### Worked example (mukey 459310, Zamora loam, Davis CA — tested live)

| Horizon | Depth cm | OM% | OC% (OM/1.724) | BD g/cm³ | Frag% | Stock t C/ha |
|---|---|---|---|---|---|---|
| H1 | 0–25 | 3.0 | 1.74 | 1.48 | 0 | 64.4 |
| H2 | 25–102 | 0.75 | 0.435 | 1.40 | 0 | 46.9 (full) / to 100 cm: 45.7 |
| H3 | 102–130 | 0.25 | 0.145 | 1.45 | 5 | 5.6 |
| H4 | 130–152 | 0.25 | 0.145 | 1.53 | 28 | 3.5 |

**0–30 cm ≈ 67 t C/ha · 0–100 cm ≈ 110 t C/ha.** (0–30 takes H1 fully plus 5 cm of H2.)

### Python helper (optional)

```python
def soc_stock(horizons, depth_limit_cm):
    """horizons: list of dicts with hzdept_r, hzdepb_r, om_r, dbthirdbar_r, fragvol_r (all numeric or None)."""
    total, gaps = 0.0, []
    for h in horizons:
        top, bot = h["hzdept_r"], h["hzdepb_r"]
        if top is None or bot is None:
            continue
        bot = min(bot, depth_limit_cm)
        if bot <= top:
            continue
        thick = bot - top
        om, bd = h["om_r"], h["dbthirdbar_r"]
        if om is None or bd is None:
            gaps.append(h.get("hzname"))
            continue
        frag = h["fragvol_r"] or 0.0
        total += (om / 1.724) * bd * thick * (1 - frag / 100.0)
    return total, gaps   # tonnes C/ha, list of skipped horizons
```

## Caveats (always surface)

- SSURGO values are **representative/estimated**, not measured at this point. SOC here is a **modeled baseline**, not a field measurement.
- Real SOC varies with management, tillage, and recent land-use change — a survey value won't capture that.
- SSURGO is 1:24,000-scale mapping: it describes soils **mapped in this area**, not this exact spot.
- For measured carbon you'd need lab data (KSSL) or on-site sampling — out of scope here.

## Units

OM/OC in % by weight · bulk density g/cm³ · depth cm · SOC stock t C/ha (= Mg C/ha). 1 t C/ha = 0.1 kg C/m². To CO₂-equivalent: × 3.67.
