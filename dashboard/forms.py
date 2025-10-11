from django import forms
from .models import Product

class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ["product_name", "description","max_temp", "min_temp", "price_eth", "quantity_available"]
        widgets = {
            "product_name": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "max_temp": forms.NumberInput(attrs={"class": "form-control", "step": "0.1"}),
            "min_temp": forms.NumberInput(attrs={"class": "form-control", "step": "0.1"}),
            "price_eth": forms.NumberInput(attrs={"class": "form-control", "step": "0.00000001"}),
            "quantity_available": forms.NumberInput(attrs={"class": "form-control"}),
        }
 