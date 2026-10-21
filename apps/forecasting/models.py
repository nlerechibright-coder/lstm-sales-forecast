from django.db import models
from django.conf import settings
from django.db import transaction
from accounts.models import Company
from inventory.models import Product
import json


class FeatureRegistry:
    """
    Central registry of all engineered features available to the LSTM pipeline.
    """
    
    ACTIVE_FEATURES = [
        {'name': 'sales_quantity',   'type': 'target', 'source': 'sales_model', 'required': True},
        {'name': 'sales_amount',     'type': 'numeric', 'source': 'sales_model', 'required': True},
        {'name': 'discount',         'type': 'numeric', 'source': 'sales_model', 'required': False},
        {'name': 'day_of_week_sin',  'type': 'cyclic',  'source': 'engineered',  'required': True},
        {'name': 'day_of_week_cos',  'type': 'cyclic',  'source': 'engineered',  'required': True},
        {'name': 'month_sin',        'type': 'cyclic',  'source': 'engineered',  'required': True},
        {'name': 'month_cos',        'type': 'cyclic',  'source': 'engineered',  'required': True},
        {'name': 'is_weekend',       'type': 'binary',  'source': 'engineered',  'required': True},
    ]
    
    PLANNED_FEATURES = [
        {'name': 'is_holiday',     'type': 'binary',  'source': 'external_factors', 'required': False},
        {'name': 'promotion_flag', 'type': 'binary',  'source': 'promotions',       'required': False},
        {'name': 'temperature',    'type': 'numeric', 'source': 'external_factors', 'required': False},
        {'name': 'inflation_rate', 'type': 'numeric', 'source': 'external_factors', 'required': False},
    ]
    
    @classmethod
    def get_active_features(cls) -> list:
        return cls.ACTIVE_FEATURES
    
    @classmethod
    def get_feature_names(cls) -> list:
        return [f['name'] for f in cls.ACTIVE_FEATURES]
    
    @classmethod
    def get_target_feature(cls) -> str:
        for f in cls.ACTIVE_FEATURES:
            if f['type'] == 'target':
                return f['name']
        return 'sales_quantity'


class ForecastModel(models.Model):
    """
    Stores metadata and the serialized artifact for a company's trained LSTM model.
    """
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name='forecast_models'
    )
    
    name = models.CharField(max_length=255, default="Company-Wide LSTM")
    version = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=False, db_index=True)
    
    architecture = models.JSONField(
        default=dict,
        help_text="Snapshot of model hyperparameters (lookback, units, dropout, etc.)"
    )
    
    feature_config = models.JSONField(
        default=dict,
        help_text="Snapshot of FeatureRegistry.ACTIVE_FEATURES at training time"
    )
    
    model_path = models.CharField(
        max_length=500,
        blank=True,
        null=True,
        help_text="Filesystem path to the saved .keras or .h5 model file"
    )
    
    scaler_config = models.JSONField(
        default=dict,
        help_text="Serialized MinMaxScaler parameters (feature_ranges, etc.)"
    )
    
    training_samples = models.PositiveIntegerField(default=0)
    validation_loss = models.FloatField(blank=True, null=True)
    training_loss = models.FloatField(blank=True, null=True)
    epochs_trained = models.PositiveIntegerField(default=0)
    
    is_company_wide = models.BooleanField(default=True, db_index=True)
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name='forecast_models',
        help_text="Null = company-wide. Set = product-specific (Phase 7)."
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    trained_at = models.DateTimeField(blank=True, null=True)
    
    class Meta:
        db_table = 'forecasting_models'
        ordering = ['-is_active', '-trained_at']
        indexes = [
            models.Index(fields=['company', 'is_active', 'is_company_wide']),
            models.Index(fields=['company', 'product', 'is_active']),
        ]
    
    def __str__(self):
        scope = "company-wide" if self.is_company_wide else f"product-{self.product_id}"
        return f"{self.company.name} - {self.name} v{self.version} ({scope})"
    
    def save(self, *args, **kwargs):
        if self.is_active:
            with transaction.atomic():
                ForecastModel.objects.filter(
                    company=self.company,
                    is_active=True,
                    is_company_wide=self.is_company_wide,
                    product=self.product
                ).exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)


class ForecastRun(models.Model):
    """
    Audit trail for every training or retraining execution.
    """
    RUN_TYPES = [
        ('TRAIN', 'Initial Training'),
        ('RETRAIN', 'Retraining'),
        ('AUTO_RETRAIN', 'Scheduled Auto-Retraining'),
    ]
    
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('RUNNING', 'Running'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
        ('CANCELLED', 'Cancelled'),
    ]
    
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name='forecast_runs'
    )
    run_type = models.CharField(max_length=20, choices=RUN_TYPES, default='TRAIN')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    
    data_start_date = models.DateField(blank=True, null=True)
    data_end_date = models.DateField(blank=True, null=True)
    total_records = models.PositiveIntegerField(default=0)
    
    mae = models.FloatField(blank=True, null=True, help_text="Mean Absolute Error")
    rmse = models.FloatField(blank=True, null=True, help_text="Root Mean Squared Error")
    mape = models.FloatField(blank=True, null=True, help_text="Mean Absolute Percentage Error")
    
    error_message = models.TextField(blank=True, null=True)
    training_log = models.TextField(
        blank=True,
        null=True,
        help_text="Full training log output including epoch progress"
    )
    
    forecast_model = models.ForeignKey(
        ForecastModel,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='runs'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(blank=True, null=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    
    class Meta:
        db_table = 'forecasting_runs'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Run {self.id} - {self.company.name} - {self.run_type} - {self.status}"
    
    @property
    def duration_seconds(self):
        """Calculate training duration in seconds."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None
    
    @property
    def duration_display(self):
        """Human-readable duration."""
        seconds = self.duration_seconds
        if seconds is None:
            return "—"
        if seconds < 60:
            return f"{int(seconds)}s"
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes}m {secs}s"


class ForecastResult(models.Model):
    """
    Individual forecast predictions generated by a trained model.
    Includes business intelligence metrics (revenue, profit).
    """
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name='forecast_results'
    )
    forecast_model = models.ForeignKey(
        ForecastModel,
        on_delete=models.CASCADE,
        related_name='results'
    )
    
    forecast_date = models.DateField(help_text="The date being predicted")
    predicted_quantity = models.FloatField()
    
    lower_bound = models.FloatField(blank=True, null=True)
    upper_bound = models.FloatField(blank=True, null=True)
    
    actual_quantity = models.FloatField(blank=True, null=True)
    
    # Forecast metadata
    forecast_horizon = models.PositiveIntegerField(
        default=60,
        help_text="Number of days ahead this forecast was generated for"
    )
    
    input_features = models.JSONField(
        default=dict,
        blank=True,
        help_text="Snapshot of feature values fed into the model for this prediction"
    )
    
    # BUSINESS INTELLIGENCE FIELDS
    average_selling_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        help_text="Average selling price used for revenue calculation"
    )
    expected_revenue = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        blank=True,
        null=True,
        help_text="Predicted Quantity × Average Selling Price"
    )
    expected_profit = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        blank=True,
        null=True,
        help_text="(Selling Price - Cost Price) × Predicted Quantity (if cost_price available)"
    )
    historical_avg_revenue = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        blank=True,
        null=True,
        help_text="Historical average daily revenue for comparison"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'forecasting_results'
        ordering = ['forecast_date']
        unique_together = ('forecast_model', 'forecast_date')
        indexes = [
            models.Index(fields=['company', 'forecast_date']),
            models.Index(fields=['company', 'created_at']),
        ]
    
    def __str__(self):
        return f"{self.company.name} - {self.forecast_date}: {self.predicted_quantity:.2f}"
    
    @property
    def error(self) -> float:
        """Absolute error if actual is known."""
        if self.actual_quantity is not None:
            return abs(self.predicted_quantity - self.actual_quantity)
        return None
    
    @property
    def confidence_percentage(self) -> float:
        """Calculate confidence percentage based on bounds."""
        if self.lower_bound is not None and self.upper_bound is not None and self.predicted_quantity > 0:
            spread = self.upper_bound - self.lower_bound
            return max(0, min(100, 100 - (spread / self.predicted_quantity * 100)))
        return None
    
    @property
    def revenue_difference(self) -> float:
        """Difference between expected and historical average revenue."""
        if self.expected_revenue and self.historical_avg_revenue:
            return float(self.expected_revenue - self.historical_avg_revenue)
        return None
    
    @property
    def revenue_percentage_change(self) -> float:
        """Percentage change compared to historical average revenue."""
        if self.expected_revenue and self.historical_avg_revenue and self.historical_avg_revenue > 0:
            return float((self.expected_revenue - self.historical_avg_revenue) / self.historical_avg_revenue * 100)
        return None