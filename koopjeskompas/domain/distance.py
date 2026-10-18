from math import asin, cos, radians, sin, sqrt

from koopjeskompas.domain.models import Coordinates

EARTH_RADIUS_KM = 6371.0  # mean radius


def haversine_km(a: Coordinates, b: Coordinates) -> float:
    """Great-circle distance between two points on Earth, in kilometres."""
    lat_a, lon_a = radians(a.latitude), radians(a.longitude)
    lat_b, lon_b = radians(b.latitude), radians(b.longitude)

    hav_theta = (
        sin((lat_b - lat_a) / 2) ** 2
        + cos(lat_a) * cos(lat_b) * sin((lon_b - lon_a) / 2) ** 2
    )
    # Floating-point rounding can push hav_theta a hair above 1 for antipodal points.
    theta = 2 * asin(sqrt(min(hav_theta, 1.0)))
    return EARTH_RADIUS_KM * theta
