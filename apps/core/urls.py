from django.urls import path
from .views import (
    upload_sales_data,
    download_sales_template,
    mapping_interface,
    confirm_mapping,
    execute_import,
)

urlpatterns = [
    path('upload/', upload_sales_data, name='upload_sales'),
    path('upload/template/', download_sales_template, name='download_sales_template'),
    path('mapping/<int:job_id>/', mapping_interface, name='mapping_interface'),
    path('mapping/confirm/', confirm_mapping, name='confirm_mapping'),
    path('import/<int:job_id>/', execute_import, name='execute_import'),
]