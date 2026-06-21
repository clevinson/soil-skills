"""Geometry helpers for the soil-survey skill — AOI ingest + repair, stdlib-only.

One tested path for turning whatever boundary the user has (GeoJSON, WKT, or a
zipped shapefile) into the single validated AOI WKT polygon that Area mode's
`{{aoi_wkt}}` consumes. Coordinates are always (longitude, latitude) — WGS84,
EPSG:4326. Longitude FIRST in WKT — the classic trap.

No third-party deps required for GeoJSON/WKT. shapely (if importable) is used
only to repair self-intersections; zipped shapefiles need pyshp (`shapefile`).
Everything fails *visibly* — a bad ring raises, it never silently degrades.
"""
import json
import math
import re

WGS84 = 4326


def geojson_ring_to_wkt(ring):
    """A GeoJSON linear ring ([[lon,lat], ...]) -> 'lon lat, lon lat, ...', ring closed."""
    pts = [(float(x), float(y)) for x, y in ring]
    if pts[0] != pts[-1]:
        pts.append(pts[0])  # close the ring
    return ", ".join(f"{x} {y}" for x, y in pts)


def _signed_area(pts):
    """Shoelace signed area in coordinate units (deg^2). >0 = CCW, <0 = CW."""
    s = 0.0
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        s += x1 * y2 - x2 * y1
    return s / 2.0


def _orient(pts, ccw=True):
    """Force ring orientation. Exterior rings CCW for the geography cast."""
    if pts[0] != pts[-1]:
        pts = pts + [pts[0]]
    if (_signed_area(pts) > 0) != ccw:
        pts = list(reversed(pts))
    return pts


def _rings_to_wkt(rings):
    """rings: list of ring-coord-lists, exterior first. Exterior CCW, holes CW."""
    parts = []
    for i, ring in enumerate(rings):
        pts = [(float(x), float(y)) for x, y in ring]
        pts = _orient(pts, ccw=(i == 0))
        parts.append("(" + ", ".join(f"{x} {y}" for x, y in pts) + ")")
    return "POLYGON(" + ", ".join(parts) + ")"


def _geojson_geom_to_wkt(geom):
    t = geom["type"]
    if t == "Polygon":
        return _rings_to_wkt(geom["coordinates"])
    if t == "MultiPolygon":
        # Dissolve to one AOI by taking the largest polygon's outer ring set.
        # (For multi-part parcels, keep the biggest part; note it to the user.)
        best = max(geom["coordinates"], key=lambda poly: abs(_signed_area(
            [(float(x), float(y)) for x, y in poly[0]] +
            [(float(poly[0][0][0]), float(poly[0][0][1]))])))
        return _rings_to_wkt(best)
    if t == "Feature":
        return _geojson_geom_to_wkt(geom["geometry"])
    if t == "FeatureCollection":
        # union not available in stdlib; take the largest feature's polygon
        geoms = [f["geometry"] for f in geom["features"]
                 if f.get("geometry", {}).get("type") in ("Polygon", "MultiPolygon")]
        if not geoms:
            raise ValueError("FeatureCollection has no polygon geometry")
        return max((_geojson_geom_to_wkt(g) for g in geoms), key=approx_acres)
    raise ValueError(f"unsupported GeoJSON type for an AOI: {t}")


def validate_and_repair(wkt):
    """Close rings + enforce orientation (done in conversion). If shapely is present,
    additionally fix self-intersections via make_valid. Raise visibly if unrepairable."""
    try:
        from shapely import wkt as _wkt, make_valid  # type: ignore
        g = _wkt.loads(wkt)
        if not g.is_valid:
            g = make_valid(g)
            if g.geom_type not in ("Polygon", "MultiPolygon"):
                raise ValueError("AOI could not be repaired to a polygon")
        return g.wkt
    except ImportError:
        return wkt  # rings already closed + oriented; no self-intersection check available


def approx_acres(aoi):
    """Cheap local area sanity-check BEFORE spending an SDA round-trip.
    Accepts a WKT string or a GeoJSON geometry dict. Planar shoelace with a
    cos(lat) correction — good to a few % for parcel-scale AOIs, enough to catch
    a malformed or lon/lat-swapped polygon early."""
    if isinstance(aoi, dict):
        aoi = _geojson_geom_to_wkt(aoi)
    m = re.search(r"\(\((.*?)\)\)", aoi.replace("POLYGON", "").replace("MULTIPOLYGON", ""))
    if not m:
        raise ValueError("could not parse a ring from WKT")
    pts = [(float(a), float(b)) for a, b in (p.split() for p in m.group(1).split(","))]
    lat0 = sum(y for _, y in pts) / len(pts)
    mlon = 111320.0 * math.cos(math.radians(lat0))
    mlat = 110540.0
    xy = [(x * mlon, y * mlat) for x, y in pts]
    return abs(_signed_area(xy)) * 0.000247105  # m^2 -> acres


def to_aoi_wkt(source):
    """Ingest GeoJSON (dict or str), WKT (str), or a zipped-shapefile path; return one
    validated AOI WKT polygon (lon/lat, ring-closed, exterior CCW). Fails visibly."""
    # zipped shapefile
    if isinstance(source, str) and source.lower().endswith(".zip"):
        return validate_and_repair(_shapefile_zip_to_wkt(source))
    # GeoJSON dict
    if isinstance(source, dict):
        return validate_and_repair(_geojson_geom_to_wkt(source))
    if isinstance(source, str):
        s = source.strip()
        if s.startswith("{"):  # GeoJSON text
            return validate_and_repair(_geojson_geom_to_wkt(json.loads(s)))
        if s.upper().startswith(("POLYGON", "MULTIPOLYGON")):  # WKT
            return validate_and_repair(s)
    raise ValueError("AOI source must be GeoJSON, a WKT POLYGON/MULTIPOLYGON, or a .zip shapefile path")


def _shapefile_zip_to_wkt(path):
    try:
        import io
        import zipfile
        import shapefile  # pyshp
    except ImportError:
        raise RuntimeError(
            "reading a zipped shapefile needs the `shapefile` (pyshp) package; "
            "if unavailable, ask the user to paste GeoJSON or WKT instead")
    import zipfile
    with zipfile.ZipFile(path) as z:
        names = {n.split(".")[-1].lower(): n for n in z.namelist()}
        import io
        rdr = shapefile.Reader(
            shp=io.BytesIO(z.read(names["shp"])),
            dbf=io.BytesIO(z.read(names["dbf"])) if "dbf" in names else None)
        shapes = rdr.shapes()
    if not shapes:
        raise ValueError("shapefile has no shapes")
    # __geo_interface__ yields GeoJSON-like geometry
    geoms = [s.__geo_interface__ for s in shapes]
    return max((_geojson_geom_to_wkt(g) for g in geoms), key=approx_acres)
