from django.db import models

# Create your models here.
from django.db import models
from django.contrib.auth.models import User

class UserProfile(models.Model):
    ROLE_CHOICES = [
        ("buyer", "Buyer"),
        ("seller", "Seller"),
        ("distributor", "Distributor"),
        ("admin", "Admin"),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE)
    middle_name = models.CharField(max_length=100, blank=True, null=True)
    phone = models.CharField(max_length=20)
    organization = models.CharField(max_length=255, blank=True, null=True)
    user_role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    wallet_address = models.CharField(max_length=255, blank=True, null=True)
    id_upload = models.FileField(upload_to="ids/", blank=True, null=True)
    address_upload = models.FileField(upload_to="addresses/", blank=True, null=True)

    def __str__(self):
        return f"{self.user.username} - {self.user_role}"
