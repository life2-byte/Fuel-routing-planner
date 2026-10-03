import csv
from decimal import Decimal

from django.core.management.base import BaseCommand

from myapp.models import FuelStation

US_STATES = set(
    "AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO "
    "MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split()
)


class Command(BaseCommand):
    help = "Import fuel stations from CSV (cheapest price per station, US only)"

    def add_arguments(self, parser):
        parser.add_argument("csv_path", type=str)

    def handle(self, *args, **opts):
        best = {}
        skipped = 0
        with open(opts["csv_path"], newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                state = row["State"].strip().upper()
                if state not in US_STATES:
                    skipped += 1
                    continue
                sid = int(row["OPIS Truckstop ID"])
                price = Decimal(row["Retail Price"])
                if sid not in best or price < best[sid]["price"]:
                    best[sid] = {
                        "opis_id": sid,
                        "name": row["Truckstop Name"].strip(),
                        "address": row["Address"].strip(),
                        "city": row["City"].strip(),
                        "state": state,
                        "rack_id": int(row["Rack ID"]),
                        "price": price,
                    }

        FuelStation.objects.all().delete()
        FuelStation.objects.bulk_create(
            [FuelStation(**d) for d in best.values()], batch_size=1000
        )
        self.stdout.write(self.style.SUCCESS(
            f"Imported {len(best)} stations, skipped {skipped} non-US rows"
        ))