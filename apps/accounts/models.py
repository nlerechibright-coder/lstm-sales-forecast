from django.contrib.auth.models import AbstractUser
from django.db import models


class Company(models.Model):
    """
    Represents a tenant/organization in the multi-tenant architecture.
    Every user belongs to exactly one company.
    """
    name = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'accounts_companies'
        verbose_name = 'Company'
        verbose_name_plural = 'Companies'

    def __str__(self):
        return self.name


class CustomUser(AbstractUser):
    """
    Extended user model with role-based access control and company affiliation.
    """
    ROLE_CHOICES = [
        ('owner', 'Owner'),
        ('manager', 'Manager'),
        ('supervisor', 'Supervisor'),
        ('sales_staff', 'Sales Staff'),
    ]

    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default='sales_staff',
        help_text="User's role within their organization"
    )
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name='users',
        null=True,
        blank=True
    )

    class Meta:
        db_table = 'accounts_custom_users'

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"