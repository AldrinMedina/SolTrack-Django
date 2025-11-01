from django import forms
from .models import CustomUser
from django.core.validators import FileExtensionValidator

ROLE_CHOICES = [
    ("buyer", "Buyer"),
    ("seller", "Seller"),
    ("admin", "Admin"),
]


class BaseUserInfoForm(forms.Form):
    full_name = forms.CharField(max_length=255, label="Full name")
    email = forms.EmailField(label="Email address")
    password = forms.CharField(widget=forms.PasswordInput, label="Password")
    confirm_password = forms.CharField(widget=forms.PasswordInput, label="Confirm password")

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
    organization = forms.CharField(max_length=255, required=False)
    address = forms.CharField(max_length=500, required=False)
    m_address = forms.CharField(max_length=255, required=False, label="MetaMask Wallet Address")

class SellerOrgForm(forms.Form):
    organization = forms.CharField(max_length=255, required=False)
    address = forms.CharField(max_length=500, required=False)
    m_address = forms.CharField(max_length=255, required=False, label="MetaMask Wallet Address")
    business_license = forms.FileField(
        required=False,
        validators=[FileExtensionValidator(['pdf', 'jpg', 'jpeg', 'png'])],
        help_text="PDF, JPG, PNG (MAX. 5MB)"
    )

    
class LoginForm(forms.Form):
    email = forms.EmailField()
    password = forms.CharField(widget=forms.PasswordInput)
