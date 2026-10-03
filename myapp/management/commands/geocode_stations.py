import csv
import re

from django.core.management.base import BaseCommand

from myapp.models import FuelStation


def norm(name: str) -> str:
    n = name.lower().strip()
    n = re.sub(r"\bst\.?\s", "saint ", n)
    n = re.sub(r"\bste\.?\s", "sainte ", n)
    n = re.sub(r"\bft\.?\s", "fort ", n)
    n = re.sub(r"\bmt\.?\s", "mount ", n)
    n = re.sub(r"[^a-z0-9 ]", "", n)
    return re.sub(r"\s+", "", n)


class Command(BaseCommand):
    help = "Fill lat/lng for stations using GeoNames US.txt (city + state match)"

    def add_arguments(self, parser):
        parser.add_argument("geonames_path", type=str)

    def handle(self, *args, **opts):
        # (norm_city, state) -> (population, lat, lng); biggest population wins
        places = {}
        with open(opts["geonames_path"], encoding="utf-8", newline="") as f:
            for row in csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE):
                if len(row) < 15 or row[6] != "P":  # populated places only
                    continue
                state = row[10]
                try:
                    pop = int(row[14] or 0)
                    lat, lng = float(row[4]), float(row[5])
                except ValueError:
                    continue
                for nm in {row[1], row[2]}:
                    key = (norm(nm), state)
                    if key not in places or pop > places[key][0]:
                        places[key] = (pop, lat, lng)

        stations = list(FuelStation.objects.all())
        missing = set()
        for s in stations:
            hit = places.get((norm(s.city), s.state))
            if hit:
                s.lat, s.lng = hit[1], hit[2]
            else:
                missing.add((s.city, s.state))

        FuelStation.objects.bulk_update(stations, ["lat", "lng"], batch_size=1000)

        done = sum(1 for s in stations if s.lat is not None)
        self.stdout.write(self.style.SUCCESS(
            f"Geocoded {done}/{len(stations)} stations"
        ))
        if missing:
            self.stdout.write(f"Unmatched cities ({len(missing)}): {sorted(missing)[:30]}")