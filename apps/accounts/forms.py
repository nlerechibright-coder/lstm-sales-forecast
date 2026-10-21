from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.core.exceptions import ValidationError
from .models import CustomUser, Company


class OwnerRegistrationForm(UserCreationForm):
    """
    Registration form for company owners.
    Creates both a Company and a CustomUser with role='owner'.
    """
    company_name = forms.CharField(
        max_length=255,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'e.g. ACME Corporation'
        })
    )
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'owner@company.com'
        })
    )

    class Meta:
        model = CustomUser
        fields = ('username', 'email', 'password1', 'password2')
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Username'}),
        }

    def clean_company_name(self):
        company_name = self.cleaned_data.get('company_name')
        if Company.objects.filter(name__iexact=company_name).exists():
            raise ValidationError(
                'An organization with this name already exists. Please choose a different name or contact the existing owner.'
            )
        return company_name

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = 'owner'
        company_name = self.cleaned_data['company_name']

        company = Company.objects.create(name=company_name)
        user.company = company

        if commit:
            user.save()
        return user


class StaffCreationForm(UserCreationForm):
    """
    Form for owners to create staff accounts within their company.
    """
    email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'staff@company.com'
        })
    )
    role = forms.ChoiceField(
        choices=[
            ('manager', 'Manager'),
            ('supervisor', 'Supervisor'),
            ('sales_staff', 'Sales Staff'),
        ],
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    class Meta:
        model = CustomUser
        fields = ('username', 'email', 'role', 'password1', 'password2')
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Username'}),
        }