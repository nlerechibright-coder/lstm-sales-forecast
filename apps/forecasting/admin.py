from django.contrib import admin
from forecasting.models import ForecastModel, ForecastRun, ForecastResult


@admin.register(ForecastModel)
class ForecastModelAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'company', 'name', 'version', 'is_active',
        'is_company_wide', 'trained_at', 'created_at'
    )
    list_filter = ('is_active', 'is_company_wide', 'company')
    search_fields = ('name', 'company__name')
    readonly_fields = ('created_at', 'updated_at', 'trained_at')
    ordering = ('-is_active', '-trained_at')


@admin.register(ForecastRun)
class ForecastRunAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'company', 'run_type', 'status',
        'total_records', 'mae', 'rmse', 'mape',
        'created_at', 'completed_at'
    )
    list_filter = ('status', 'run_type', 'company')
    search_fields = ('company__name', 'error_message')
    readonly_fields = ('created_at', 'completed_at')
    ordering = ('-created_at',)


@admin.register(ForecastResult)
class ForecastResultAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'company', 'forecast_model', 'forecast_date',
        'predicted_quantity', 'actual_quantity', 'error'
    )
    list_filter = ('forecast_model', 'company')
    search_fields = ('company__name',)
    readonly_fields = ('created_at',)
    ordering = ('forecast_date',)