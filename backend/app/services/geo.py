"""C5: pure geometry for geofences (no database, no I/O).

Coordinates are WGS84 decimal degrees; polygon rings are `[lon, lat]` pairs (GeoJSON order). Distances are metres.
Within a fence the Earth is treated as flat (local equirectangular projection about the fence's reference point). That
is accurate to well under a metre for fences up to a few tens of kilometres, which is the supported range
(`MAX_EXTENT_M`); larger fences are refused instead of being evaluated inaccurately.

`signed_distance_m` is NEGATIVE inside a fence and POSITIVE outside; 0 is exactly on the boundary.
Unsupported on purpose: fences crossing the antimeridian, fences beyond +/-85 degrees latitude, self-intersecting or
zero-area polygons.
"""
from __future__ import annotations

import math
from typing import Any

EARTH_RADIUS_M = 6_371_008.8
MAX_POLYGON_VERTICES = 500
MIN_RADIUS_M = 1.0
MAX_RADIUS_M = 100_000.0
MAX_EXTENT_M = 100_000.0
MAX_ABS_LAT = 85.0


class GeometryError(ValueError):
    """Invalid or unsupported geometry. The message is safe to return to API clients."""


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi, dlmb = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def _project(lat: float, lon: float, ref_lat: float, ref_lon: float) -> tuple[float, float]:
    """Local east/north metres of (lat, lon) relative to the reference point."""
    x = math.radians(lon - ref_lon) * EARTH_RADIUS_M * math.cos(math.radians(ref_lat))
    y = math.radians(lat - ref_lat) * EARTH_RADIUS_M
    return x, y


def _check_lat_lon(lat: Any, lon: Any, what: str) -> tuple[float, float]:
    if isinstance(lat, bool) or isinstance(lon, bool) or not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
        raise GeometryError(f"{what}: latitude and longitude must be numbers")
    if not (math.isfinite(lat) and math.isfinite(lon)):
        raise GeometryError(f"{what}: coordinates must be finite")
    if abs(lat) > MAX_ABS_LAT:
        raise GeometryError(f"{what}: latitude must be within +/-{MAX_ABS_LAT:g} degrees (polar fences are unsupported)")
    if not -180.0 <= lon <= 180.0:
        raise GeometryError(f"{what}: longitude must be within -180..180")
    return float(lat), float(lon)


def normalize_geometry(geometry_type: str, geometry: dict[str, Any]) -> dict[str, Any]:
    """Validate and canonicalise. Circle: {center:{lat,lon}, radius_m}. Polygon: {ring:[[lon,lat],...]} (open ring)."""
    if geometry_type == "CIRCLE":
        c = geometry.get("center") or {}
        lat, lon = _check_lat_lon(c.get("lat"), c.get("lon"), "center")
        r = geometry.get("radius_m")
        if isinstance(r, bool) or not isinstance(r, (int, float)) or not math.isfinite(r):
            raise GeometryError("radius_m must be a number")
        if not MIN_RADIUS_M <= r <= MAX_RADIUS_M:
            raise GeometryError(f"radius_m must be between {MIN_RADIUS_M:g} and {MAX_RADIUS_M:g} metres")
        return {"center": {"lat": lat, "lon": lon}, "radius_m": float(r)}
    if geometry_type == "POLYGON":
        ring = geometry.get("ring")
        if not isinstance(ring, list) or not all(isinstance(p, (list, tuple)) and len(p) == 2 for p in ring):
            raise GeometryError("ring must be a list of [lon, lat] pairs")
        pts = [_check_lat_lon(p[1], p[0], f"vertex {i}") for i, p in enumerate(ring)]
        if len(pts) > 1 and pts[0] == pts[-1]:
            pts.pop()  # accept a closed ring, store it open
        if not 3 <= len(pts) <= MAX_POLYGON_VERTICES:
            raise GeometryError(f"a polygon needs 3..{MAX_POLYGON_VERTICES} distinct vertices")
        if len(set(pts)) != len(pts):
            raise GeometryError("polygon has repeated vertices")
        if max(p[1] for p in pts) - min(p[1] for p in pts) > 180:
            raise GeometryError("fences crossing the antimeridian are unsupported")
        ref_lat, ref_lon = pts[0]
        xy = [_project(la, lo, ref_lat, ref_lon) for la, lo in pts]
        if max(abs(v) for p in xy for v in p) > MAX_EXTENT_M:
            raise GeometryError(f"polygon extent exceeds {MAX_EXTENT_M / 1000:g} km from its first vertex")
        if abs(_area(xy)) < 1.0:
            raise GeometryError("polygon has (almost) zero area")
        if _self_intersects(xy):
            raise GeometryError("polygon edges must not cross each other")
        return {"ring": [[lo, la] for la, lo in pts]}
    raise GeometryError(f"unsupported geometry type {geometry_type!r}")


def _area(xy: list[tuple[float, float]]) -> float:
    return 0.5 * sum(xy[i][0] * xy[(i + 1) % len(xy)][1] - xy[(i + 1) % len(xy)][0] * xy[i][1] for i in range(len(xy)))


def _orient(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _segments_cross(p1, p2, p3, p4) -> bool:
    d1, d2, d3, d4 = _orient(p3, p4, p1), _orient(p3, p4, p2), _orient(p1, p2, p3), _orient(p1, p2, p4)
    return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)) and 0 not in (d1, d2, d3, d4)


def _self_intersects(xy: list[tuple[float, float]]) -> bool:
    n = len(xy)
    for i in range(n):
        a1, a2 = xy[i], xy[(i + 1) % n]
        for j in range(i + 2, n):
            if i == 0 and j == n - 1:
                continue  # adjacent through the closing edge
            if _segments_cross(a1, a2, xy[j], xy[(j + 1) % n]):
                return True
    return False


def _point_segment_distance(p: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    seg2 = dx * dx + dy * dy
    t = 0.0 if seg2 == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / seg2))
    return math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy))


def _inside_polygon(p: tuple[float, float], xy: list[tuple[float, float]]) -> bool:
    inside = False
    n = len(xy)
    for i in range(n):
        (x1, y1), (x2, y2) = xy[i], xy[(i + 1) % n]
        if (y1 > p[1]) != (y2 > p[1]) and p[0] < (x2 - x1) * (p[1] - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def bbox(geometry_type: str, geometry: dict[str, Any], margin_m: float = 0.0) -> tuple[float, float, float, float]:
    """(min_lat, min_lon, max_lat, max_lon) of the fence grown by `margin_m` -- a cheap pre-filter."""
    if geometry_type == "CIRCLE":
        c, r = geometry["center"], geometry["radius_m"] + margin_m
        dlat = math.degrees(r / EARTH_RADIUS_M)
        dlon = math.degrees(r / (EARTH_RADIUS_M * max(0.01, math.cos(math.radians(c["lat"])))))
        return c["lat"] - dlat, c["lon"] - dlon, c["lat"] + dlat, c["lon"] + dlon
    lats = [p[1] for p in geometry["ring"]]
    lons = [p[0] for p in geometry["ring"]]
    mid = (min(lats) + max(lats)) / 2
    dlat = math.degrees(margin_m / EARTH_RADIUS_M)
    dlon = math.degrees(margin_m / (EARTH_RADIUS_M * max(0.01, math.cos(math.radians(mid)))))
    return min(lats) - dlat, min(lons) - dlon, max(lats) + dlat, max(lons) + dlon


def signed_distance_m(geometry_type: str, geometry: dict[str, Any], lat: float, lon: float) -> float:
    """Metres from the point to the fence boundary: negative inside, positive outside."""
    if geometry_type == "CIRCLE":
        c = geometry["center"]
        return haversine_m(c["lat"], c["lon"], lat, lon) - geometry["radius_m"]
    ring = geometry["ring"]
    ref_lat, ref_lon = ring[0][1], ring[0][0]
    xy = [_project(p[1], p[0], ref_lat, ref_lon) for p in ring]
    pt = _project(lat, lon, ref_lat, ref_lon)
    d = min(_point_segment_distance(pt, xy[i], xy[(i + 1) % len(xy)]) for i in range(len(xy)))
    return -d if _inside_polygon(pt, xy) else d
