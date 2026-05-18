from astra.places.geolocation import _bounding_box


def test_bounding_box_contains_point() -> None:
    min_lat, max_lat, min_lon, max_lon = _bounding_box(45.04, 38.98, 50.0)
    assert min_lat < 45.04 < max_lat
    assert min_lon < 38.98 < max_lon
