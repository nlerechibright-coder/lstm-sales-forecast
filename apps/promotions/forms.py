from django import forms
from .models import Promotion
from inventory.models import Product


class PromotionForm(forms.ModelForm):
    """Form for creating and editing promotions."""
    
    products = forms.ModelMultipleChoiceField(
        queryset=Product.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="Select specific products or leave empty to apply to all products"
    )
    
    class Meta:
        model = Promotion
        fields = [
            'promotion_name',
            'description',
            'discount_type',
            'discount_value',
            'start_date',
            'end_date',
            'status',
        ]
        widgets = {
            'promotion_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter promotion name'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Optional description'
            }),
            'discount_type': forms.Select(attrs={
                'class': 'form-select'
            }),
            'discount_value': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0'
            }),
            'start_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'end_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'status': forms.Select(attrs={
                'class': 'form-select'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        company = kwargs.pop('company', None)
        super().__init__(*args, **kwargs)
        
        # Filter products by company
        if company:
            self.fields['products'].queryset = Product.objects.filter(company=company)
    
    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        discount_value = cleaned_data.get('discount_value')
        discount_type = cleaned_data.get('discount_type')
        
        if start_date and end_date and start_date > end_date:
            raise forms.ValidationError("End date must be after start date.")
        
        if discount_value is not None:
            if discount_type == 'percentage' and (discount_value < 0 or discount_value > 100):
                raise forms.ValidationError("Percentage discount must be between 0 and 100.")
            elif discount_type == 'fixed' and discount_value < 0:
                raise forms.ValidationError("Fixed discount cannot be negative.")
        
        return cleaned_data