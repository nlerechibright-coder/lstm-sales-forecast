from django.db import models
from accounts.models import Company
from inventory.models import Product


class Promotion(models.Model):
    """
    Promotions and discounts for products.
    Company-scoped for multi-tenant isolation.
    """
    DISCOUNT_TYPE_CHOICES = [
        ('percentage', 'Percentage (%)'),
        ('fixed', 'Fixed Amount (₦)'),
    ]
    
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('expired', 'Expired'),
    ]
    
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name='promotions'
    )
    promotion_name = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    
    # Discount configuration
    discount_type = models.CharField(max_length=20, choices=DISCOUNT_TYPE_CHOICES, default='percentage')
    discount_value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text="Percentage (0-100) or fixed amount in Naira"
    )
    
    # Date range
    start_date = models.DateField()
    end_date = models.DateField()
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    
    # Product assignment (null = applies to all products)
    products = models.ManyToManyField(
        Product,
        blank=True,
        related_name='promotions',
        help_text="Leave empty to apply to all products"
    )
    
    # Metadata
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'promotions_promotion'
        ordering = ['-start_date']
        verbose_name = 'Promotion'
        verbose_name_plural = 'Promotions'
        indexes = [
            models.Index(fields=['company', 'status']),
            models.Index(fields=['company', 'start_date', 'end_date']),
        ]
    
    def __str__(self):
        return f"{self.promotion_name} - {self.get_discount_type_display()}"
    
    def save(self, *args, **kwargs):
        # Auto-set status based on dates
        from datetime import date
        today = date.today()
        
        if self.end_date < today:
            self.status = 'expired'
            self.is_active = False
        elif self.start_date <= today <= self.end_date:
            if self.status == 'expired':
                self.status = 'active'
                self.is_active = True
        
        super().save(*args, **kwargs)
    
    @property
    def is_currently_active(self):
        """Check if promotion is currently within date range and active."""
        from datetime import date
        today = date.today()
        return (
            self.is_active and
            self.status == 'active' and
            self.start_date <= today <= self.end_date
        )
    
    def get_discount_display(self):
        """Return formatted discount string."""
        if self.discount_type == 'percentage':
            return f"{self.discount_value}%"
        else:
            return f"₦{self.discount_value:,.2f}"
    
    def calculate_discount(self, original_price):
        """Calculate discount amount for a given price."""
        if self.discount_type == 'percentage':
            return (original_price * self.discount_value) / 100
        else:
            return min(self.discount_value, original_price)