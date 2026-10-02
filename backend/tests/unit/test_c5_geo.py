"""C5: geofence geometry (pure) and schema validation."""
import math

import pytest
from pydantic import ValidationError

from app.schemas.geofence import GeofenceCreate, GeofenceUpdate
from app.services import geo

LAT, LON = 10.0, 77.0
M_PER_DEG_LAT = 111_194.9


def east(m: float, lat: float = LAT, lon: float = LON) -> tuple[float, float]:
    return lat, lon + m / (M_PER_DEG_LAT * math.cos(math.radians(lat)))


def square(half_m: float = 100.0):
    pts = [(-half_m, -half_m), (half_m, -half_m), (half_m, half_m), (-half_m, half_m)]
    ring = []
    for ex, ny in pts:
        lat = LAT + ny / M_PER_DEG_LAT
        lon = LON + ex / (M_PER_DEG_LAT * math.cos(math.radians(LAT)))
        ring.append([lon, lat])
    return {"ring": ring}


def test_circle_signed_distance():
    g = {"center": {"lat": LAT, "lon": LON}, "radius_m": 200.0}
    assert geo.signed_distance_m("CIRCLE", g, LAT, LON) == pytest.approx(-200.0, abs=0.01)
    assert geo.signed_distance_m("CIRCLE", g, *east(250)) == pytest.approx(50.0, abs=0.5)
    assert geo.signed_distance_m("CIRCLE", g, *east(150)) == pytest.approx(-50.0, abs=0.5)


def test_polygon_signed_distance_and_edges():
    g = geo.normalize_geometry("POLYGON", square(100))
    assert geo.signed_distance_m("POLYGON", g, LAT, LON) == pytest.approx(-100.0, abs=0.5)
    assert geo.signed_distance_m("POLYGON", g, *east(130)) == pytest.approx(30.0, abs=0.5)
    assert geo.signed_distance_m("POLYGON", g, *east(100)) == pytest.approx(0.0, abs=0.5)  # on the boundary


def test_concave_polygon_notch_is_outside():
    # "U" shape: the notch between the arms is outside the fence even though it is inside the bounding box.
    m = [(-100, -100), (100, -100), (100, 100), (40, 100), (40, 0), (-40, 0), (-40, 100), (-100, 100)]
    ring = [[LON + x / (M_PER_DEG_LAT * math.cos(math.radians(LAT))), LAT + y / M_PER_DEG_LAT] for x, y in m]
    g = geo.normalize_geometry("POLYGON", {"ring": ring})
    notch_lat = LAT + 60 / M_PER_DEG_LAT
    assert geo.signed_distance_m("POLYGON", g, notch_lat, LON) > 0
    assert geo.signed_distance_m("POLYGON", g, LAT - 50 / M_PER_DEG_LAT, LON) < 0


def test_closed_ring_is_accepted_and_stored_open():
    ring = square(50)["ring"]
    g = geo.normalize_geometry("POLYGON", {"ring": ring + [ring[0]]})
    assert len(g["ring"]) == 4


@pytest.mark.parametrize("gt,geometry", [
    ("CIRCLE", {"center": {"lat": 95, "lon": 0}, "radius_m": 10}),
    ("CIRCLE", {"center": {"lat": 10, "lon": 200}, "radius_m": 10}),
    ("CIRCLE", {"center": {"lat": 10, "lon": 10}, "radius_m": 0}),
    ("CIRCLE", {"center": {"lat": 10, "lon": 10}, "radius_m": 1e7}),
    ("CIRCLE", {"center": {"lat": float("nan"), "lon": 10}, "radius_m": 10}),
    ("CIRCLE", {"center": {"lat": "10", "lon": 10}, "radius_m": 10}),
    ("CIRCLE", {"center": {"lat": 89, "lon": 10}, "radius_m": 10}),            # polar
    ("POLYGON", {"ring": [[0, 0], [1, 1]]}),                                   # too few
    ("POLYGON", {"ring": [[77, 10], [77.001, 10], [77.001, 10.001], [77, 10.001]] * 1 + [[77, 10]] * 0 + [[77.001, 10]]}),
    ("POLYGON", {"ring": [[77, 10], [77.001, 10.001], [77.001, 10], [77, 10.001]]}),  # bow-tie
    ("POLYGON", {"ring": [[77, 10], [77.0001, 10], [77.0002, 10]]}),           # zero area
    ("POLYGON", {"ring": "nope"}),
    ("TRIANGLE", {}),
])
def test_invalid_geometry_rejected(gt, geometry):
    with pytest.raises(geo.GeometryError):
        geo.normalize_geometry(gt, geometry)


def test_too_many_vertices_rejected():
    ring = [[LON + 0.0001 * math.cos(2 * math.pi * i / 600), LAT + 0.0001 * math.sin(2 * math.pi * i / 600)]
            for i in range(600)]
    with pytest.raises(geo.GeometryError):
        geo.normalize_geometry("POLYGON", {"ring": ring})


def test_bbox_contains_fence_plus_margin():
    g = {"center": {"lat": LAT, "lon": LON}, "radius_m": 200.0}
    min_lat, min_lon, max_lat, max_lon = geo.bbox("CIRCLE", g, 50)
    lat, lon = east(240)
    assert min_lat <= lat <= max_lat and min_lon <= lon <= max_lon
    lat, lon = east(400)
    assert not (min_lon <= lon <= max_lon)


def _base(**kw):
    return {"name": "z", "kind": "RESTRICTED", "geometry_type": "CIRCLE",
            "geometry": {"center": {"lat": 1, "lon": 1}, "radius_m": 10}, **kw}


def test_schema_validation():
    GeofenceCreate(**_base())
    for bad in ({"alt_min_m": 100, "alt_max_m": 50}, {"confirm_count": 0}, {"boundary_tolerance_m": -1},
                {"kind": "NO_FLY"}, {"extra": 1}, {"organization_id": "x"},
                {"active_from": "2026-01-02T00:00:00+00:00", "active_until": "2026-01-01T00:00:00+00:00"},
                {"active_from": "2026-01-01T00:00:00"}):
        with pytest.raises(ValidationError):
            GeofenceCreate(**_base(**bad))
    with pytest.raises(ValidationError):
        GeofenceUpdate(organization_id="x")  # tenant can never be set from a request body
