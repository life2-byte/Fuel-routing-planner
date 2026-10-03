import hashlib

import requests
from django.core.cache import cache

OSRM_URL = "https://router.project-osrm.org/route/v1/driving"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
HEADERS = {"User-Agent": "fuel-route-assessment/1.0"}
METERS_PER_MILE = 1609.344
DAY = 60 * 60 * 24


class RoutingError(Exception):
    pass


def parse_point(value):
    """'lat,lng' string -> (lat, lng), warna None."""
    try:
        lat, lng = [float(x) for x in value.split(",")]
    except ValueError:
        return None
    if -90 <= lat <= 90 and -180 <= lng <= 180:
        return lat, lng
    return None


def geocode(place):
    """Text ya 'lat,lng' -> (lat, lng). Text ke liye Nominatim (cached)."""
    point = parse_point(place)
    if point:
        return point

    key = "geo:" + hashlib.md5(place.lower().strip().encode()).hexdigest()
    cached = cache.get(key)
    if cached:
        return cached

    resp = requests.get(
        NOMINATIM_URL,
        params={"q": place, "format": "json", "limit": 1, "countrycodes": "us"},
        headers=HEADERS,
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    if not data:
        raise RoutingError(f"Location not found in USA: {place}")

    point = (float(data[0]["lat"]), float(data[0]["lon"]))
    cache.set(key, point, 30 * DAY)
    return point


def get_route(start, finish):
    """OSRM ko ek call. Return: distance, duration, coordinates [[lng, lat], ...]."""
    slat, slng = geocode(start)
    flat, flng = geocode(finish)

    key = f"route:{slat:.4f},{slng:.4f}:{flat:.4f},{flng:.4f}"
    cached = cache.get(key)
    if cached:
        return cached

    # OSRM mein order lng,lat hota hai (ulta!)
    url = f"{OSRM_URL}/{slng},{slat};{flng},{flat}"
    resp = requests.get(
        url, params={"overview": "full", "geometries": "geojson"}, timeout=20
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != "Ok":
        raise RoutingError(f"No route found: {data.get('code')}")

    route = data["routes"][0]
    result = {
        "distance_miles": route["distance"] / METERS_PER_MILE,
        "duration_hours": route["duration"] / 3600,
        "coordinates": route["geometry"]["coordinates"],  # [[lng, lat], ...]
        "start": (slat, slng),
        "finish": (flat, flng),
    }
    cache.set(key, result, DAY)
    return result