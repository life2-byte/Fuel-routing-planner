import math
from collections import defaultdict

EARTH_RADIUS_MILES = 3958.8
MAX_RANGE_MILES = 500.0
MPG = 10.0
CORRIDOR_MILES = 10.0   # station route se itni door tak accept
ROUTE_STEP_MILES = 1.0
CELL_DEG = 0.25


class PlanError(Exception):
    pass


def haversine(lat1, lng1, lat2, lng2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (
        math.sin((p2 - p1) / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lng2 - lng1) / 2) ** 2
    )
    return 2 * EARTH_RADIUS_MILES * math.asin(min(1.0, math.sqrt(a)))


def _approx_miles(lat1, lng1, lat2, lng2):
    """Chhoti doori ke liye tez approximation."""
    dy = (lat2 - lat1) * 69.05
    dx = (lng2 - lng1) * 69.17 * math.cos(math.radians((lat1 + lat2) / 2))
    return math.hypot(dx, dy)


def build_route_points(coords, total_miles):
    """[[lng, lat], ...] -> [(lat, lng, mile)] ~1 mile spacing.
    Mile markers OSRM ki total distance ke hisaab se scale hote hain."""
    if len(coords) < 2:
        raise PlanError("Route geometry too short")

    cum = [0.0]
    for (lng1, lat1), (lng2, lat2) in zip(coords, coords[1:]):
        cum.append(cum[-1] + haversine(lat1, lng1, lat2, lng2))
    scale = total_miles / (cum[-1] or 1e-9)

    points = []
    last = None
    for (lng, lat), m in zip(coords, cum):
        m *= scale
        if last is None or m - last >= ROUTE_STEP_MILES:
            points.append((lat, lng, m))
            last = m

    end_mile = cum[-1] * scale
    if points[-1][2] < end_mile:
        points.append((coords[-1][1], coords[-1][0], end_mile))
    return points


def stations_along_route(points, stations, corridor=CORRIDOR_MILES):
    """Route ke corridor ke andar wale stations + unka mile marker."""
    grid = defaultdict(list)
    for lat, lng, mile in points:
        grid[(math.floor(lat / CELL_DEG), math.floor(lng / CELL_DEG))].append(
            (lat, lng, mile)
        )

    found = []
    for s in stations:
        ci = math.floor(s["lat"] / CELL_DEG)
        cj = math.floor(s["lng"] / CELL_DEG)
        best = None
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                for lat, lng, mile in grid.get((ci + di, cj + dj), ()):
                    d = _approx_miles(s["lat"], s["lng"], lat, lng)
                    if d <= corridor and (best is None or d < best[0]):
                        best = (d, mile)
        if best:
            found.append(
                {**s, "price": float(s["price"]), "off_route_miles": best[0], "mile": best[1]}
            )

    found.sort(key=lambda x: (x["mile"], x["price"]))
    return found


def plan_fuel(stations, total_miles, max_range=MAX_RANGE_MILES, mpg=MPG):
    """Greedy: next sasta station range mein ho to wahan tak ka hi fuel lo,
    warna tank full karo aur range ke sabse sasta station tak jao."""
    nodes = [dict(s, dest=False) for s in stations]
    nodes.append({"mile": total_miles, "price": 0.0, "dest": True})
    nodes.sort(key=lambda n: (n["mile"], n["dest"]))

    if nodes[0]["dest"]:
        raise PlanError("No fuel stations found near this route")
    if nodes[0]["mile"] > max_range:
        raise PlanError(f"No fuel station within first {max_range:.0f} miles of route")

    bought = defaultdict(float)          # node index -> miles of fuel kharida
    bought[0] += nodes[0]["mile"]        # pehle station tak pahunchne ka fuel
    cur, fuel = 0, 0.0

    while not nodes[cur]["dest"]:
        c = nodes[cur]
        limit = c["mile"] + max_range
        cheaper = None
        cheapest = None
        j = cur + 1
        while j < len(nodes) and nodes[j]["mile"] <= limit:
            if nodes[j]["price"] < c["price"]:
                cheaper = j
                break
            if cheapest is None or nodes[j]["price"] <= nodes[cheapest]["price"]:
                cheapest = j
            j += 1

        if cheaper is not None:
            dist = nodes[cheaper]["mile"] - c["mile"]
            if fuel < dist:
                bought[cur] += dist - fuel
                fuel = dist
            fuel -= dist
            cur = cheaper
        elif cheapest is not None:
            dist = nodes[cheapest]["mile"] - c["mile"]
            bought[cur] += max_range - fuel
            fuel = max_range - dist
            cur = cheapest
        else:
            raise PlanError(
                f"No fuel station within {max_range:.0f} miles after mile {c['mile']:.0f}"
            )

    stops = []
    for idx in sorted(bought):
        miles = bought[idx]
        if miles <= 1e-9:
            continue
        gallons = miles / mpg
        stops.append({**nodes[idx], "gallons": gallons, "cost": gallons * nodes[idx]["price"]})
    return stops