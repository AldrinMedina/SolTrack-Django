from django import forms
from .models import Product

class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ["product_name", "description", "price_eth", "quantity_available"]
        widgets = {
            "product_name": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "price_eth": forms.NumberInput(attrs={"class": "form-control", "step": "0.00000001"}),
            "quantity_available": forms.NumberInput(attrs={"class": "form-control"}),
        }
