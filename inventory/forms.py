from django import forms
from .models import Product, InventoryCategory, PaymentMethod


class ProductForm(forms.ModelForm):
    auto_generate_sku = forms.BooleanField(
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input',
        })
    )

    class Meta:
        model = Product
        fields = ['name', 'sku', 'category', 'base_price', 'cost_price', 'current_stock', 'reorder_level', 'auto_generate_sku']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. Rice 50kg'
            }),
            'sku': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. RICE-50KG-001 (or auto-generate)'
            }),
            'category': forms.Select(attrs={
                'class': 'form-select',
            }),
            'base_price': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0'
            }),
            'cost_price': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0'
            }),
            'current_stock': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0'
            }),
            'reorder_level': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0'
            }),
        }

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company:
            self.fields['category'].queryset = InventoryCategory.objects.filter(
                company=company, is_active=True
            ).order_by('name')
            self.fields['category'].empty_label = "-- Select Category --"


class InventoryCategoryForm(forms.ModelForm):
    class Meta:
        model = InventoryCategory
        fields = ['name', 'description', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. Food, Electronics, Beverage'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Optional description...'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
            }),
        }


class PaymentMethodForm(forms.ModelForm):
    class Meta:
        model = PaymentMethod
        fields = ['name', 'code', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. Cash Payment'
            }),
            'code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. CASH, POS, TRANSFER'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
            }),
        }