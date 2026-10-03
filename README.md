# Fuel Routing Planner (Django)

USA ke andar start aur finish location do, API route, cost-optimal fuel stops aur total fuel cost return karti hai.

- Vehicle max range: **500 miles**
- Mileage: **10 mpg**
- Fuel prices: provided CSV (`data/fuel_prices.csv`)
- Routing: **OSRM** public API (free, no key)

## Setup

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate

# 1. CSV ko DB mein import karo (sirf US stations, har station ka sabse sasta price)
python manage.py import_fuel data/fuel_prices.csv

# 2. Stations ki lat/lng bharo (ek baar, offline GeoNames data se)
wget https://download.geonames.org/export/dump/US.zip -O data/US.zip
unzip -o data/US.zip US.txt -d data/
python manage.py geocode_stations data/US.txt

python manage.py runserver
```

## API

`POST /api/route/`

```json
{
  "start": "New York, NY",
  "finish": "Los Angeles, CA"
}
```

`GET /api/route/?start=New York, NY&finish=Chicago, IL` bhi chalta hai.

`start` / `finish` text (`"Chicago, IL"`) ya coordinates (`"41.8781,-87.6298"`) ho sakte hain.

### Response (short)

```json
{
  "distance_miles": 2794.0,
  "duration_hours": 41.5,
  "fuel_stops": [
    {
      "order": 1,
      "name": "...",
      "city": "...",
      "state": "..",
      "lat": 0.0,
      "lng": 0.0,
      "price_per_gallon": 3.2,
      "mile_marker": 120.5,
      "gallons": 40.0,
      "cost": 128.0
    }
  ],
