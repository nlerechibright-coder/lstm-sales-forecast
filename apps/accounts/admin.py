from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser, Company


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'created_at')
    search_fields = ('name',)
    ordering = ('-created_at',)


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'email', 'role', 'company', 'is_active', 'date_joined')
    list_filter = ('role', 'is_active', 'company')
    search_fields = ('username', 'email', 'company__name')
    ordering = ('-date_joined',)

    fieldsets = UserAdmin.fieldsets + (
        ('Organization', {'fields': ('company', 'role')}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Organization', {'fields': ('company', 'role')}),
    )