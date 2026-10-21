from django.urls import path
from . import views

urlpatterns = [
    path('dashboard/', views.training_dashboard, name='forecasting_dashboard'),
    path('train/', views.trigger_training, name='trigger_training'),
    path('train/status/<int:run_id>/', views.training_status, name='training_status'),
    path('train/logs/<int:run_id>/', views.training_logs, name='training_logs'),
    path('train/diagnose/', views.training_diagnose, name='training_diagnose'),
    path('results/', views.forecast_results, name='forecast_results'),
    path('history/', views.forecast_history, name='forecast_history'),
    path('generate/', views.trigger_forecast, name='trigger_forecast'),
    path('models/', views.model_comparison, name='model_comparison'),
    path('models/<int:model_id>/activate/', views.activate_model, name='activate_model'),
    path('list/', views.forecast_list, name='forecast_list'),
    path('detail/<int:forecast_id>/', views.forecast_detail, name='forecast_detail'),
    path('export/<int:forecast_id>/', views.export_forecast, name='export_forecast'),
    path('delete/<int:forecast_id>/', views.delete_forecast, name='delete_forecast'),
]