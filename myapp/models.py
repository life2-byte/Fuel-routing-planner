from django.db import models


class FuelStation(models.Model):
    opis_id = models.IntegerField(unique=True)
    name = models.CharField(max_length=255)
    address = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=2, db_index=True)
    rack_id = models.IntegerField()
    price = models.DecimalField(max_digits=7, decimal_places=4, db_index=True)
    lat = models.FloatField(null=True, blank=True)
    lng = models.FloatField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["lat", "lng"])]

    def __str__(self):
        return f"{self.name} ({self.city}, {self.state}) ${self.price}"