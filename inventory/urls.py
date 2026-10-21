from django.urls import path
from . import views

urlpatterns = [
    path('', views.inventory_dashboard, name='inventory_dashboard'),
    path('list/', views.list_products, name='list_products'),
    path('add/', views.add_product, name='add_product'),
    path('detail/<int:product_id>/', views.product_detail, name='product_detail'),
    path('alerts/', views.inventory_alerts, name='inventory_alerts'),
    path('settings/', views.inventory_settings, name='inventory_settings'),
    
    # Category Management
    path('categories/', views.category_list, name='category_list'),
    path('categories/add/', views.category_add, name='category_add'),
    path('categories/<int:category_id>/edit/', views.category_edit, name='category_edit'),
    path('categories/<int:category_id>/delete/', views.category_delete, name='category_delete'),
    
    # Payment Method Management
    path('payment-methods/', views.payment_method_list, name='payment_method_list'),
    path('payment-methods/add/', views.payment_method_add, name='payment_method_add'),
    path('payment-methods/<int:method_id>/edit/', views.payment_method_edit, name='payment_method_edit'),
    path('payment-methods/<int:method_id>/delete/', views.payment_method_delete, name='payment_method_delete'),
]