from app.grid import haversine_km, hex_grid


def test_haversine_known_distance():
    # Bengaluru MG Road to Koramangala is ~5km
    d = haversine_km(12.9758, 77.6045, 12.9352, 77.6245)
    assert 4 < d < 6


def test_grid_covers_circle():
    pts = hex_grid(12.97, 77.59, 10, 3.0)
    assert all(haversine_km(12.97, 77.59, la, ln) <= 10.01 for la, ln in pts)
    # Spacing 3km over a 10km circle should give roughly area/cell ~ 40 points
    assert 25 < len(pts) < 60


def test_grid_sorted_nearest_first():
    pts = hex_grid(12.97, 77.59, 15, 3.0)
    dists = [haversine_km(12.97, 77.59, la, ln) for la, ln in pts]
    assert dists == sorted(dists)
    assert dists[0] < 0.01  # center included


def test_small_radius_has_center():
    pts = hex_grid(28.61, 77.21, 1, 3.0)
    assert len(pts) >= 1
