from django import forms
from .models import CustomUser
from django.conf import settings
from pathlib import Path
import json
from django.core.validators import FileExtensionValidator


ROLE_CHOICES = [
    ("buyer", "Buyer"),
    ("seller", "Seller"),
    ("admin", "Admin"),
]

class MultiFileInput(forms.FileInput):
    allow_multiple_selected = True

    def __init__(self, attrs=None):
        final_attrs = {'multiple': True}
        if attrs:
            final_attrs.update(attrs)
        super().__init__(attrs=final_attrs)


class BaseUserInfoForm(forms.Form):
    full_name = forms.CharField(max_length=255, label="Full name", widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Lastname, Firstname Middlename'}))
    email = forms.EmailField(label="Email address", widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'example@gmail.com'}))
    password = forms.CharField(label="Password", widget=forms.PasswordInput(attrs={'class': 'form-control', 'id': 'password'}))
    confirm_password = forms.CharField(label="Confirm password" , widget=forms.PasswordInput(attrs={'class': 'form-control', 'id': 'confirm_password'}))

    def clean(self):
        cleaned = super().clean()
        pw = cleaned.get("password")
        cpw = cleaned.get("confirm_password")
        if pw and cpw and pw != cpw:
            raise forms.ValidationError("Passwords do not match.")
        return cleaned

class BuyerUserForm(BaseUserInfoForm):
    pass

class SellerUserForm(BaseUserInfoForm):
    pass

# --- Organization forms ---
class BuyerOrgForm(forms.Form):
    organization = forms.CharField(max_length=255, required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))
    full_address = forms.CharField(required=False)
    region = forms.ChoiceField(choices=[], required=True)
    province = forms.ChoiceField(choices=[], required=True)
    city = forms.ChoiceField(choices=[], required=True)
    barangay = forms.ChoiceField(choices=[], required=True)
    m_address = forms.CharField(max_length=255, required=False, label="MetaMask Wallet Address", widget=forms.TextInput(attrs={'class': 'form-control'}))
    business_license = forms.FileField(
        required=False,
        validators=[FileExtensionValidator(['pdf', 'jpg', 'jpeg', 'png'])],
        help_text="PDF, JPG, PNG (MAX. 10MB)",
        widget=forms.FileInput(attrs={'class': 'form-control'})
    )
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Load address hierarchy
        with open(Path(settings.BASE_DIR) / "static/geo/philippines.json") as f:
            geo = json.load(f)

        # Always load REGION choices
        self.fields["region"].choices = [(r["code"], r["name"]) for r in geo]

        # If POST has region, load provinces under it
        if "region" in self.data:
            region_code = self.data.get("region")
            region = next((r for r in geo if r["code"] == region_code), None)

            if region:
                self.fields["province"].choices = [
                    (p["code"], p["name"]) for p in region["provinces"]
                ]
            else:
                self.fields["province"].choices = []
        else:
            self.fields["province"].choices = []

        # If POST has province, load cities
        if "province" in self.data:
            region_code = self.data.get("region")
            province_code = self.data.get("province")
            region = next((r for r in geo if r["code"] == region_code), None)

            if region:
                province = next((p for p in region["provinces"] if p["code"] == province_code), None)
                if province:
                    self.fields["city"].choices = [
                        (c["code"], c["name"]) for c in province["cities"]
                    ]
                else:
                    self.fields["city"].choices = []
            else:
                self.fields["city"].choices = []
        else:
            self.fields["city"].choices = []

        # If POST has city, load barangays
        if "city" in self.data:
            region_code = self.data.get("region")
            province_code = self.data.get("province")
            city_code = self.data.get("city")

            region = next((r for r in geo if r["code"] == region_code), None)
            if region:
                province = next((p for p in region["provinces"] if p["code"] == province_code), None)
                if province:
                    city = next((c for c in province["cities"] if c["code"] == city_code), None)
                    if city:
                        self.fields["barangay"].choices = [
                            (b, b) for b in city["barangays"]
                        ]
                    else:
                        self.fields["barangay"].choices = []
                else:
                    self.fields["barangay"].choices = []
            else:
                self.fields["barangay"].choices = []
        else:
            self.fields["barangay"].choices = []

class SellerOrgForm(forms.Form):
    organization = forms.CharField(max_length=255, required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))
    # address = forms.CharField(max_length=500, required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))
    full_address = forms.CharField(required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))
    region = forms.ChoiceField(choices=[], required=True)
    province = forms.ChoiceField(choices=[], required=True)
    city = forms.ChoiceField(choices=[], required=True)
    barangay = forms.ChoiceField(choices=[], required=True)
    m_address = forms.CharField(max_length=255, required=False, label="MetaMask Wallet Address", widget=forms.TextInput(attrs={'class': 'form-control'}))
    business_license = forms.FileField(
        required=False,
        validators=[FileExtensionValidator(['pdf', 'jpg', 'jpeg', 'png'])],
        help_text="PDF, JPG, PNG (MAX. 10MB)",
        widget=forms.FileInput(attrs={'class': 'form-control'})
    )
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Load address hierarchy
        with open(Path(settings.BASE_DIR) / "static/geo/philippines.json") as f:
            geo = json.load(f)

        # Always load REGION choices
        self.fields["region"].choices = [(r["code"], r["name"]) for r in geo]

        # If POST has region, load provinces under it
        if "region" in self.data:
            region_code = self.data.get("region")
            region = next((r for r in geo if r["code"] == region_code), None)

            if region:
                self.fields["province"].choices = [
                    (p["code"], p["name"]) for p in region["provinces"]
                ]
            else:
                self.fields["province"].choices = []
        else:
            self.fields["province"].choices = []

        # If POST has province, load cities
        if "province" in self.data:
            region_code = self.data.get("region")
            province_code = self.data.get("province")
            region = next((r for r in geo if r["code"] == region_code), None)

            if region:
                province = next((p for p in region["provinces"] if p["code"] == province_code), None)
                if province:
                    self.fields["city"].choices = [
                        (c["code"], c["name"]) for c in province["cities"]
                    ]
                else:
                    self.fields["city"].choices = []
            else:
                self.fields["city"].choices = []
        else:
            self.fields["city"].choices = []

        # If POST has city, load barangays
        if "city" in self.data:
            region_code = self.data.get("region")
            province_code = self.data.get("province")
            city_code = self.data.get("city")

            region = next((r for r in geo if r["code"] == region_code), None)
            if region:
                province = next((p for p in region["provinces"] if p["code"] == province_code), None)
                if province:
                    city = next((c for c in province["cities"] if c["code"] == city_code), None)
                    if city:
                        self.fields["barangay"].choices = [
                            (b, b) for b in city["barangays"]
                        ]
                    else:
                        self.fields["barangay"].choices = []
                else:
                    self.fields["barangay"].choices = []
            else:
                self.fields["barangay"].choices = []
        else:
            self.fields["barangay"].choices = []


    
class LoginForm(forms.Form):
    email = forms.EmailField()
    password = forms.CharField(widget=forms.PasswordInput)
