from django.urls import path
from . import views

urlpatterns = [
    path('', views.promotion_list, name='promotion_list'),
    path('create/', views.promotion_create, name='promotion_create'),
    path('<int:promotion_id>/edit/', views.promotion_edit, name='promotion_edit'),
    path('<int:promotion_id>/delete/', views.promotion_delete, name='promotion_delete'),
    path('<int:promotion_id>/toggle/', views.promotion_toggle_status, name='promotion_toggle_status'),
]