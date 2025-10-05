from django import forms
from django.contrib.auth.models import User
from .models import UserProfile

class RegistrationForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput)
    confirm_password = forms.CharField(widget=forms.PasswordInput)

    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email"]

    # extra profile fields
    phone = forms.CharField(max_length=20)
    middle_name = forms.CharField(required=False)
    organization = forms.CharField(required=False)
    user_role = forms.ChoiceField(choices=UserProfile.ROLE_CHOICES)
    wallet_address = forms.CharField(required=False)
    id_upload = forms.FileField(required=False)
    address_upload = forms.FileField(required=False)

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        confirm_password = cleaned_data.get("confirm_password")

        if password and confirm_password and password != confirm_password:
            raise forms.ValidationError("Passwords do not match.")

        return cleaned_data
