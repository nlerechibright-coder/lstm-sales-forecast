from django.db import models
from accounts.models import Company
from core.models import UploadJob
from inventory.models import Product, PaymentMethod


class ColumnMapping(models.Model):
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name='column_mappings'
    )
    header_name = models.CharField(max_length=255, db_index=True)
    field_name = models.CharField(max_length=100, db_index=True)
    confidence = models.FloatField(
        default=1.0,
        help_text="Mapping confidence score (0.0 to 1.0). 1.0 = user-confirmed."
    )
    usage_count = models.PositiveIntegerField(default=1)
    last_used = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'sales_column_mappings'
        unique_together = ('company', 'header_name', 'field_name')
        ordering = ['-usage_count', '-last_used']

    def __str__(self):
        return f"{self.company.name}: '{self.header_name}' → '{self.field_name}'"


class DataImport(models.Model):
    upload_job = models.ForeignKey(
        UploadJob,
        on_delete=models.CASCADE,
        related_name='data_imports'
    )
    row_number = models.PositiveIntegerField()
    raw_data = models.JSONField(help_text="Original row data before normalization")
    normalized_data = models.JSONField(
        blank=True,
        null=True,
        help_text="Row data after normalization"
    )
    status = models.CharField(
        max_length=20,
        choices=[
            ('PENDING', 'Pending'),
            ('VALIDATED', 'Validated'),
            ('IMPORTED', 'Imported'),
            ('FAILED', 'Failed'),
            ('SKIPPED', 'Skipped'),
        ],
        default='PENDING'
    )
    error_message = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'sales_data_imports'
        unique_together = ('upload_job', 'row_number')
        ordering = ['row_number']

    def __str__(self):
        return f"Import {self.id} - Job {self.upload_job.id} - Row {self.row_number} - {self.status}"


class Customer(models.Model):
    """
    Company-scoped customer database for sales transactions.
    """
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name='customers'
    )
    name = models.CharField(max_length=255)
    phone = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True, null=True, help_text="Internal notes about the customer")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'sales_customers'
        verbose_name = 'Customer'
        verbose_name_plural = 'Customers'
        ordering = ['name']
        indexes = [
            models.Index(fields=['company', 'name']),
            models.Index(fields=['company', 'is_active']),
        ]

    def __str__(self):
        return f"{self.name} ({self.company.name})"


class SalesTransaction(models.Model):
    """
    Header record for each sales transaction.
    Links to Customer, PaymentMethod, and contains aggregate totals.
    """
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name='sales_transactions'
    )
    customer = models.ForeignKey(
        Customer,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='transactions',
        help_text="Walk-in customer if null"
    )
    payment_method = models.ForeignKey(
        PaymentMethod,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='transactions'
    )
    transaction_date = models.DateTimeField(auto_now_add=True)
    total_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0.00
    )
    total_discount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0.00
    )
    notes = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(
        'accounts.CustomUser',
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='created_transactions'
    )

    class Meta:
        db_table = 'sales_transactions'
        verbose_name = 'Sales Transaction'
        verbose_name_plural = 'Sales Transactions'
        ordering = ['-transaction_date']
        indexes = [
            models.Index(fields=['company', 'transaction_date']),
            models.Index(fields=['company', 'customer']),
        ]

    def __str__(self):
        customer_name = self.customer.name if self.customer else "Walk-in"
        return f"Transaction #{self.id} - {customer_name} - {self.transaction_date.strftime('%Y-%m-%d %H:%M')}"


class SalesTransactionItem(models.Model):
    """
    Line item for each product in a sales transaction.
    """
    transaction = models.ForeignKey(
        SalesTransaction,
        on_delete=models.CASCADE,
        related_name='items'
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name='transaction_items'
    )
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )
    discount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0.00,
        help_text="Discount amount for this line item"
    )
    subtotal = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Calculated: (quantity * unit_price) - discount"
    )

    class Meta:
        db_table = 'sales_transaction_items'
        verbose_name = 'Transaction Item'
        verbose_name_plural = 'Transaction Items'

    def __str__(self):
        return f"{self.product.name} x {self.quantity}"

    def save(self, *args, **kwargs):
        """Auto-calculate subtotal before saving."""
        self.subtotal = (self.quantity * self.unit_price) - self.discount
        super().save(*args, **kwargs)


class Sales(models.Model):
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name='sales_records'
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='sales'
    )
    date = models.DateField(db_index=True)
    sales_quantity = models.IntegerField()
    sales_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        blank=True,
        null=True
    )
    discount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        blank=True,
        null=True,
        help_text="Absolute monetary discount amount (not percentage)"
    )
    promotion = models.ForeignKey(
        'promotions.Promotion',
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='sales'
    )
    source_import = models.ForeignKey(
        DataImport,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='sales_records',
        help_text="Audit link back to the original import row"
    )
    source_transaction = models.ForeignKey(
        SalesTransaction,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='sales_records',
        help_text="Link to the transaction this sale came from"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'sales_data'
        verbose_name = 'Sales Record'
        verbose_name_plural = 'Sales Records'
        ordering = ['-date']
        indexes = [
            models.Index(fields=['company', 'date']),
            models.Index(fields=['company', 'product', 'date']),
        ]

    def __str__(self):
        return f"{self.company.name} - {self.date} - Qty: {self.sales_quantity}"