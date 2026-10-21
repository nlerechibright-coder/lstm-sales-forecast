from django.db import models
from accounts.models import Company, CustomUser
from inventory.models import Product
from django.core.validators import MinValueValidator
from decimal import Decimal


class Supplier(models.Model):
    """
    Supplier/Vendor management.
    Company-scoped for multi-tenant isolation.
    """
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('blacklisted', 'Blacklisted'),
    ]
    
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name='suppliers'
    )
    name = models.CharField(max_length=255, help_text="Supplier/Vendor name")
    contact_person = models.CharField(max_length=255, blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    
    # Performance tracking
    total_orders = models.PositiveIntegerField(default=0)
    total_spent = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    average_delivery_days = models.FloatField(blank=True, null=True)
    
    created_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_suppliers'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'procurement_suppliers'
        verbose_name = 'Supplier'
        verbose_name_plural = 'Suppliers'
        ordering = ['name']
        indexes = [
            models.Index(fields=['company', 'status']),
            models.Index(fields=['company', 'name']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.company.name})"
    
    @property
    def active_orders_count(self):
        return self.purchase_orders.filter(status__in=['pending', 'ordered']).count()


class PurchaseOrder(models.Model):
    """
    Purchase Order header.
    Tracks procurement from supplier.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('ordered', 'Ordered'),
        ('partial', 'Partially Received'),
        ('received', 'Received'),
        ('cancelled', 'Cancelled'),
    ]
    
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name='purchase_orders'
    )
    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT,
        related_name='purchase_orders'
    )
    
    order_number = models.CharField(
        max_length=50,
        unique=True,
        help_text="Auto-generated PO number"
    )
    order_date = models.DateField()
    expected_delivery = models.DateField(blank=True, null=True)
    actual_delivery = models.DateField(blank=True, null=True)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    total_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0,
        help_text="Auto-calculated from line items"
    )
    
    notes = models.TextField(blank=True, null=True)
    
    created_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_purchase_orders'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'procurement_purchase_orders'
        verbose_name = 'Purchase Order'
        verbose_name_plural = 'Purchase Orders'
        ordering = ['-order_date', '-created_at']
        indexes = [
            models.Index(fields=['company', 'status']),
            models.Index(fields=['company', 'order_date']),
            models.Index(fields=['supplier', 'status']),
        ]
    
    def __str__(self):
        return f"PO-{self.order_number} - {self.supplier.name}"
    
    def save(self, *args, **kwargs):
        # Auto-generate order number if not provided
        if not self.order_number:
            last_po = PurchaseOrder.objects.filter(company=self.company).order_by('-id').first()
            if last_po:
                # Extract number from last PO and increment
                try:
                    last_num = int(last_po.order_number.split('-')[-1])
                    new_num = last_num + 1
                except (ValueError, IndexError):
                    new_num = 1
            else:
                new_num = 1
            self.order_number = f"PO-{new_num:05d}"
        
        # Calculate total amount from items
        if self.pk:
            self.total_amount = sum(item.total_cost for item in self.items.all())
        
        super().save(*args, **kwargs)
    
    @property
    def items_count(self):
        return self.items.count()
    
    @property
    def received_items_count(self):
        return self.items.filter(quantity_received__gt=0).count()
    
    @property
    def delivery_status(self):
        if self.status == 'received':
            return 'Delivered'
        elif self.status == 'partial':
            return 'Partially Delivered'
        elif self.status == 'ordered':
            return 'In Transit'
        else:
            return 'Pending'


class PurchaseOrderItem(models.Model):
    """
    Line item for each product in a purchase order.
    """
    purchase_order = models.ForeignKey(
        PurchaseOrder,
        on_delete=models.CASCADE,
        related_name='items'
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name='purchase_order_items'
    )
    
    quantity_ordered = models.PositiveIntegerField(
        validators=[MinValueValidator(1)]
    )
    quantity_received = models.PositiveIntegerField(default=0)
    
    unit_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    total_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Auto-calculated: quantity_ordered × unit_cost"
    )
    
    notes = models.TextField(blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'procurement_purchase_order_items'
        verbose_name = 'Purchase Order Item'
        verbose_name_plural = 'Purchase Order Items'
    
    def __str__(self):
        return f"{self.product.name} × {self.quantity_ordered}"
    
    def save(self, *args, **kwargs):
        # Auto-calculate total cost
        self.total_cost = self.quantity_ordered * self.unit_cost
        super().save(*args, **kwargs)
    
    @property
    def pending_quantity(self):
        return self.quantity_ordered - self.quantity_received


class SupplierInvoice(models.Model):
    """
    Supplier invoice for purchase orders.
    Supports file upload (PDF, Excel, CSV).
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('paid', 'Paid'),
        ('rejected', 'Rejected'),
    ]
    
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name='supplier_invoices'
    )
    purchase_order = models.ForeignKey(
        PurchaseOrder,
        on_delete=models.CASCADE,
        related_name='invoices',
        blank=True,
        null=True
    )
    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT,
        related_name='invoices'
    )
    
    invoice_number = models.CharField(max_length=100)
    invoice_date = models.DateField()
    due_date = models.DateField(blank=True, null=True)
    
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=15, decimal_places=2)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    # File upload
    invoice_file = models.FileField(
        upload_to='procurement/invoices/%Y/%m/',
        blank=True,
        null=True,
        help_text="Upload PDF, Excel, or CSV invoice"
    )
    
    notes = models.TextField(blank=True, null=True)
    
    created_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_invoices'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'procurement_supplier_invoices'
        verbose_name = 'Supplier Invoice'
        verbose_name_plural = 'Supplier Invoices'
        ordering = ['-invoice_date']
        unique_together = ('company', 'invoice_number')
        indexes = [
            models.Index(fields=['company', 'status']),
            models.Index(fields=['supplier', 'status']),
        ]
    
    def __str__(self):
        return f"Invoice {self.invoice_number} - {self.supplier.name}"
    
    def save(self, *args, **kwargs):
        # Auto-calculate total
        self.total_amount = self.amount + self.tax_amount
        super().save(*args, **kwargs)


class PurchaseHistory(models.Model):
    """
    Audit log for all completed purchases.
    Created automatically when purchase order is received.
    """
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name='purchase_history'
    )
    purchase_order = models.ForeignKey(
        PurchaseOrder,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='history_records'
    )
    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT,
        related_name='history_records'
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name='purchase_history'
    )
    
    quantity = models.PositiveIntegerField()
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2)
    total_cost = models.DecimalField(max_digits=12, decimal_places=2)
    
    purchase_date = models.DateField()
    received_date = models.DateField()
    
    created_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'procurement_purchase_history'
        verbose_name = 'Purchase History'
        verbose_name_plural = 'Purchase History'
        ordering = ['-received_date', '-created_at']
        indexes = [
            models.Index(fields=['company', 'purchase_date']),
            models.Index(fields=['supplier', 'purchase_date']),
            models.Index(fields=['product', 'purchase_date']),
        ]
    
    def __str__(self):
        return f"{self.product.name} × {self.quantity} from {self.supplier.name}"