from django import forms
from .models import Customer, SalesTransaction, SalesTransactionItem
from inventory.models import Product, PaymentMethod


class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = ['name', 'phone', 'email', 'address', 'city', 'is_active', 'notes']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. John Doe or ACME Corp'
            }),
            'phone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '+234 800 000 0000'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'email@example.com'
            }),
            'address': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Street address...'
            }),
            'city': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'City'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Internal notes...'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
            }),
        }


class SalesTransactionForm(forms.ModelForm):
    customer = forms.ModelChoiceField(
        queryset=Customer.objects.none(),
        required=False,
        empty_label="Walk-in Customer",
        widget=forms.Select(attrs={
            'class': 'form-select',
        })
    )
    payment_method = forms.ModelChoiceField(
        queryset=PaymentMethod.objects.none(),
        required=False,
        empty_label="Select Payment Method",
        widget=forms.Select(attrs={
            'class': 'form-select',
        })
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 2,
            'placeholder': 'Optional notes...'
        })
    )

    class Meta:
        model = SalesTransaction
        fields = ['customer', 'payment_method', 'notes']

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company:
            self.fields['customer'].queryset = Customer.objects.filter(
                company=company, is_active=True
            )
            self.fields['payment_method'].queryset = PaymentMethod.objects.filter(
                company=company, is_active=True
            )


class SalesTransactionItemForm(forms.ModelForm):
    product = forms.ModelChoiceField(
        queryset=Product.objects.none(),
        widget=forms.Select(attrs={
            'class': 'form-select product-select',
        })
    )
    quantity = forms.IntegerField(
        min_value=1,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'min': '1',
        })
    )
    unit_price = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'step': '0.01',
        })
    )
    discount = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
        initial=0.00,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'step': '0.01',
        })
    )

    class Meta:
        model = SalesTransactionItem
        fields = ['product', 'quantity', 'unit_price', 'discount']

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company:
            self.fields['product'].queryset = Product.objects.filter(
                company=company
            ).select_related('category')