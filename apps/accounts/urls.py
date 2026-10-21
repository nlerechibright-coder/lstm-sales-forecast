from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path('register/', views.register_owner, name='register_owner'),
    path('login/', views.user_login, name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login', http_method_names=['get', 'post']), name='logout'),
    path('dashboard/', views.dashboard_router, name='accounts_dashboard'),
    path('staff/create/', views.create_staff, name='create_staff'),
]
