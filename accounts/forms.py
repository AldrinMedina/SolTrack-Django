from django import forms
from .models import CustomUser

ROLE_CHOICES = [
    ("buyer", "Buyer"),
    ("seller", "Seller"),
    ("admin", "Admin"),
]


class RegistrationForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput)
    confirm_password = forms.CharField(widget=forms.PasswordInput)
    business_license = forms.FileField(required=False)

    class Meta:
        model = CustomUser
        fields = ['full_name', 'email', 'm_address', 'role', 'password', 'organization']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Limit roles to Buyer/Seller only
        self.fields['role'].choices = [
            ('Buyer', 'Buyer'),
            ('Seller', 'Seller')
        ]

    def clean(self):
        cleaned_data = super().clean()
        pw = cleaned_data.get('password')
        cpw = cleaned_data.get('confirm_password')

        if pw and cpw and pw != cpw:
            raise forms.ValidationError("Passwords do not match.")
        return cleaned_data

    
class LoginForm(forms.Form):
    email = forms.EmailField()
    password = forms.CharField(widget=forms.PasswordInput)
