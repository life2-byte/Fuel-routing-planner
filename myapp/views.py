import hashlib
import json
from urllib.parse import urlencode

import requests
from django.core.cache import cache
from django.http import HttpResponse, JsonResponse
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .fuel_planner import (
    CORRIDOR_MILES,
    MAX_RANGE_MILES,
    MPG,
    PlanError,
    build_route_points,
    plan_fuel,
    stations_along_route,
)
from .models import FuelStation
from .routing_service import RoutingError, get_route


def _read_params(request):
    if request.method == "POST":
        try:
            body = json.loads(request.body or b"{}")
        except json.JSONDecodeError:
            body = {}
        if not isinstance(body, dict) or not body:
            body = request.POST
    else:
        body = request.GET
    return str(body.get("start") or "").strip(), str(body.get("finish") or "").strip()


def build_plan(start, finish):
    route = get_route(start, finish)  # OSRM ko ek hi call
    points = build_route_points(route["coordinates"], route["distance_miles"])

    lats = [p[0] for p in points]
    lngs = [p[1] for p in points]
    margin = 0.3
    candidates = list(
        FuelStation.objects.filter(
            lat__isnull=False,
            lat__gte=min(lats) - margin,
            lat__lte=max(lats) + margin,
            lng__gte=min(lngs) - margin,
            lng__lte=max(lngs) + margin,
        ).values("name", "address", "city", "state", "price", "lat", "lng")
    )

    near = stations_along_route(points, candidates)
    stops = plan_fuel(near, route["distance_miles"])

    fuel_stops = [
        {
            "order": i,
            "name": s["name"],
            "address": s["address"],
            "city": s["city"],
            "state": s["state"],
            "lat": s["lat"],
            "lng": s["lng"],
            "price_per_gallon": round(s["price"], 3),
            "mile_marker": round(s["mile"], 1),
            "off_route_miles": round(s["off_route_miles"], 1),
            "gallons": round(s["gallons"], 2),
            "cost": round(s["cost"], 2),
        }
        for i, s in enumerate(stops, 1)
    ]

    return {
        "start": {"query": start, "lat": route["start"][0], "lng": route["start"][1]},
        "finish": {"query": finish, "lat": route["finish"][0], "lng": route["finish"][1]},
        "distance_miles": round(route["distance_miles"], 1),
        "duration_hours": round(route["duration_hours"], 2),
        "fuel_stops": fuel_stops,
        "total_gallons": round(sum(s["gallons"] for s in stops), 2),
        "total_cost": round(sum(s["cost"] for s in stops), 2),
        "assumptions": {
            "max_range_miles": MAX_RANGE_MILES,
            "mpg": MPG,
            "station_corridor_miles": CORRIDOR_MILES,
            "note": "Vehicle starts near-empty; first stop's gallons include fuel to reach it. "
            "Station location = city center.",
        },
        "route": {
            "type": "Feature",
            "properties": {},
            "geometry": {
                "type": "LineString",
                "coordinates": [[round(lng, 5), round(lat, 5)] for lat, lng, _ in points],
            },
        },
    }


@csrf_exempt
@require_http_methods(["GET", "POST"])
def plan_route(request):
    start, finish = _read_params(request)
    if not start or not finish:
        return JsonResponse({"error": "start and finish are required"}, status=400)

    key = "plan:" + hashlib.md5(f"{start.lower()}|{finish.lower()}".encode()).hexdigest()
    payload = cache.get(key)
    if payload is None:
        try:
            payload = build_plan(start, finish)
        except (RoutingError, PlanError) as e:
            return JsonResponse({"error": str(e)}, status=400)
        except requests.RequestException:
            return JsonResponse({"error": "Routing service unavailable, try again"}, status=502)
        cache.set(key, payload, 60 * 60)

    payload = dict(payload)
    payload["map_url"] = (
        request.build_absolute_uri(reverse("map"))
        + "?"
        + urlencode({"start": start, "finish": finish})
    )
    return JsonResponse(payload)


MAP_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>Fuel Route Planner</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<style>
body{margin:0;font-family:system-ui,sans-serif}
#bar{padding:10px;display:flex;gap:8px;flex-wrap:wrap;background:#111}
#bar input{padding:6px;flex:1;min-width:160px}
#bar button{padding:6px 14px}
#info{padding:8px 12px;background:#f3f3f3}
#map{height:calc(100vh - 100px)}
</style></head>
<body>
<div id="bar">
  <input id="s" placeholder="Start (e.g. New York, NY)">
  <input id="f" placeholder="Finish (e.g. Chicago, IL)">
  <button id="go">Plan route</button>
</div>
<div id="info">Enter start and finish in the USA.</div>
<div id="map"></div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const map = L.map('map').setView([39.5, -98.35], 4);
L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}',
  {maxZoom: 18, attribution: 'Tiles &copy; Esri'}).addTo(map);
const layer = L.layerGroup().addTo(map);
const info = document.getElementById('info');
function line(t){ const d = document.createElement('div'); d.textContent = t; return d; }

async function plan(){
  const s = document.getElementById('s').value.trim();
  const f = document.getElementById('f').value.trim();
  if(!s || !f) return;
  info.textContent = 'Planning...';
  layer.clearLayers();
  try{
    const r = await fetch('/api/route/?' + new URLSearchParams({start: s, finish: f}));
    const d = await r.json();
    if(!r.ok){ info.textContent = d.error || 'Error'; return; }
    const route = L.geoJSON(d.route, {style: {color: '#2563eb', weight: 4}}).addTo(layer);
    L.marker([d.start.lat, d.start.lng]).bindPopup('Start').addTo(layer);
    L.marker([d.finish.lat, d.finish.lng]).bindPopup('Finish').addTo(layer);
    d.fuel_stops.forEach(st => {
      const el = document.createElement('div');
      el.append(line('#' + st.order + ' ' + st.name), line(st.city + ', ' + st.state),
        line('$' + st.price_per_gallon + '/gal'),
        line(st.gallons + ' gal = $' + st.cost), line('mile ' + st.mile_marker));
      L.circleMarker([st.lat, st.lng], {radius: 8, color: '#dc2626', fillOpacity: 0.9})
        .bindPopup(el).addTo(layer);
    });
    map.fitBounds(route.getBounds());
    info.textContent = d.distance_miles + ' mi | ' + d.fuel_stops.length + ' fuel stops | '
      + d.total_gallons + ' gal | total fuel cost $' + d.total_cost;
  }catch(e){ info.textContent = 'Request failed'; }
}
document.getElementById('go').onclick = plan;
const q = new URLSearchParams(location.search);
if(q.get('start') && q.get('finish')){
  document.getElementById('s').value = q.get('start');
  document.getElementById('f').value = q.get('finish');
  plan();
}
</script></body></html>"""


def map_page(request):
    return HttpResponse(MAP_HTML)