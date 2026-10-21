from django.urls import path
from . import views

urlpatterns = [
    # Dashboard
    path('', views.procurement_dashboard, name='procurement_dashboard'),

    # Suppliers
    path('suppliers/', views.supplier_list, name='supplier_list'),
    path('suppliers/add/', views.supplier_add, name='supplier_add'),
    path('suppliers/<int:supplier_id>/', views.supplier_detail, name='supplier_detail'),
    path('suppliers/<int:supplier_id>/edit/', views.supplier_edit, name='supplier_edit'),

    # Purchase Orders
    path('orders/', views.purchase_order_list, name='purchase_order_list'),
    path('orders/add/', views.purchase_order_add, name='purchase_order_add'),
    path('orders/<int:order_id>/', views.purchase_order_detail, name='purchase_order_detail'),
    path('orders/<int:order_id>/receive/', views.receive_purchase_order, name='receive_purchase_order'),
    path('orders/<int:order_id>/cancel/', views.cancel_purchase_order, name='cancel_purchase_order'),

    # Invoices
    path('invoices/', views.invoice_list, name='invoice_list'),
    path('invoices/add/', views.invoice_add, name='invoice_add'),
    path('invoices/bulk-upload/', views.invoice_bulk_upload, name='invoice_bulk_upload'),
    path('invoices/<int:invoice_id>/', views.invoice_detail, name='invoice_detail'),

    # Purchase History
    path('history/', views.purchase_history, name='purchase_history'),
]