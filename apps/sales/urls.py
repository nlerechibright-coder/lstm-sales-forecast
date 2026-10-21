from django.urls import path
from . import views

urlpatterns = [
    # Sales Entry
    path('entry/', views.sales_entry, name='sales_entry'),
    
    # Customer Management
    path('customers/', views.customer_list, name='customer_list'),
    path('customers/add/', views.customer_add, name='customer_add'),
    path('customers/<int:customer_id>/edit/', views.customer_edit, name='customer_edit'),
    path('customers/<int:customer_id>/', views.customer_detail, name='customer_detail'),
    path('customers/<int:customer_id>/delete/', views.customer_delete, name='customer_delete'),
    
    # Transaction Management
    path('transactions/', views.transaction_list, name='transaction_list'),
    path('transactions/<int:transaction_id>/', views.transaction_detail, name='transaction_detail'),
    
    # API Endpoints
    path('api/products/search/', views.product_search, name='product_search'),
]