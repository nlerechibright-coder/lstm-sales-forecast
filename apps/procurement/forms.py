from django import forms
from .models import Supplier, PurchaseOrder, PurchaseOrderItem, SupplierInvoice


class SupplierForm(forms.ModelForm):
    class Meta:
        model = Supplier
        fields = ['name', 'contact_person', 'phone', 'email', 'address', 'status']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Supplier name'}),
            'contact_person': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Contact person'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+234 800 000 0000'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'email@example.com'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Address'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
        }


class PurchaseOrderForm(forms.ModelForm):
    class Meta:
        model = PurchaseOrder
        fields = ['supplier', 'order_date', 'expected_delivery', 'notes']
        widgets = {
            'supplier': forms.Select(attrs={'class': 'form-select'}),
            'order_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'expected_delivery': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Optional notes'}),
        }


class PurchaseOrderItemForm(forms.ModelForm):
    class Meta:
        model = PurchaseOrderItem
        fields = ['product', 'quantity_ordered', 'unit_cost', 'notes']
        widgets = {
            'product': forms.Select(attrs={'class': 'form-select'}),
            'quantity_ordered': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
            'unit_cost': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0.01'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Optional notes'}),
        }


class SupplierInvoiceForm(forms.ModelForm):
    class Meta:
        model = SupplierInvoice
        fields = ['purchase_order', 'supplier', 'invoice_number', 'invoice_date', 'due_date',
                  'amount', 'tax_amount', 'invoice_file', 'notes']
        widgets = {
            'purchase_order': forms.Select(attrs={'class': 'form-select'}),
            'supplier': forms.Select(attrs={'class': 'form-select'}),
            'invoice_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Invoice number'}),
            'invoice_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'due_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'tax_amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'invoice_file': forms.FileInput(attrs={'class': 'form-control', 'accept': '.pdf,.xlsx,.xls,.csv'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }


class BulkInvoiceUploadForm(forms.Form):
    """Form for uploading a compiled CSV/Excel purchase report."""
    file = forms.FileField(
        label='Purchase Report File',
        help_text='Upload a CSV or Excel file containing purchase records from your accounting software.',
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': '.csv,.xlsx,.xls',
        })
    )
    auto_create_suppliers = forms.BooleanField(
        required=False,
        initial=True,
        label='Auto-create missing suppliers',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    auto_create_products = forms.BooleanField(
        required=False,
        initial=False,
        label='Auto-create missing products',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )