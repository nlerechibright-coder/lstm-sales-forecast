from django.db import models
from accounts.models import Company
from django.db.models import Max


class InventoryCategory(models.Model):
    """
    Product categories for inventory organization.
    Company-scoped to allow each organization to define their own categories.
    """
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name='inventory_categories'
    )
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'inventory_categories'
        verbose_name = 'Inventory Category'
        verbose_name_plural = 'Inventory Categories'
        unique_together = ('company', 'name')
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.company.name})"


class PaymentMethod(models.Model):
    """
    Payment methods accepted by the company.
    Company-scoped to allow customization.
    """
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name='payment_methods'
    )
    name = models.CharField(max_length=50)
    code = models.CharField(max_length=20, help_text="Short code like CASH, POS, TRANSFER")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'inventory_payment_methods'
        verbose_name = 'Payment Method'
        verbose_name_plural = 'Payment Methods'
        unique_together = ('company', 'code')
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.company.name})"


class Product(models.Model):
    company = models.ForeignKey(
        Company, 
        on_delete=models.CASCADE, 
        related_name='products',
        help_text="The company organization silo this product profile belongs to."
    )
    name = models.CharField(max_length=255)
    sku = models.CharField(
        max_length=100, 
        verbose_name="SKU / Product Code",
        help_text="Stock Keeping Unit unique identification tag.",
        blank=True,
        null=True
    )
    category = models.ForeignKey(
        InventoryCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='products',
        help_text="Product category for organization"
    )
    base_price = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        verbose_name="Base Selling Price"
    )
    cost_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Cost Price",
        blank=True,
        null=True,
        help_text="Optional: Used for profit calculations"
    )
    current_stock = models.IntegerField(
        default=0, 
        verbose_name="Current Stock Level"
    )
    reorder_level = models.IntegerField(
        default=10, 
        verbose_name="Safety Stock / Reorder Point"
    )
    auto_generate_sku = models.BooleanField(
        default=False,
        help_text="Auto-generate SKU based on category and sequence"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'inventory_products'
        verbose_name = 'Product Profiles'
        unique_together = ('company', 'sku')

    def __str__(self):
        return f"{self.name} ({self.sku}) - {self.company.name}"

    def save(self, *args, **kwargs):
        """Auto-generate SKU if enabled and not provided."""
        if self.auto_generate_sku and not self.sku and self.category:
            prefix = self.category.name[:4].upper()
            
            last_product = Product.objects.filter(
                company=self.company,
                sku__startswith=f"{prefix}-"
            ).order_by('-sku').first()
            
            if last_product:
                try:
                    last_num = int(last_product.sku.split('-')[-1])
                    next_num = last_num + 1
                except (ValueError, IndexError):
                    next_num = 1
            else:
                next_num = 1
            
            self.sku = f"{prefix}-{next_num:04d}"
        
        super().save(*args, **kwargs)