from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponseForbidden
from django.db import transaction
from .models import CustomUser, Company
from .forms import OwnerRegistrationForm, StaffCreationForm


def register_owner(request):
    """
    Public endpoint for new company owners to register.
    Creates a new Company and assigns the user as owner.
    """
    if request.method == 'POST':
        form = OwnerRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, f'Welcome, {user.username}! Your organization has been created.')
            return redirect('dashboard')
    else:
        form = OwnerRegistrationForm()
    return render(request, 'accounts/register.html', {'form': form})


def user_login(request):
    """
    Authenticate and log in a user.
    """
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('dashboard')
        else:
            messages.error(request, 'Invalid username or password.')
    return render(request, 'accounts/login.html')


@login_required
def user_logout(request):
    """
    Log out the current user.
    """
    logout(request)
    messages.info(request, 'You have been logged out.')
    return redirect('login')


@login_required
def dashboard_router(request):
    """
    Route authenticated users to their role-specific dashboard.
    """
    user = request.user
    company = user.company

    if user.role == 'owner':
        staff_members = CustomUser.objects.filter(company=company).exclude(id=user.id)
        context = {'staff_members': staff_members}
        return render(request, 'accounts/dashboard_owner.html', context)

    elif user.role == 'manager':
        return render(request, 'accounts/dashboard_manager.html')

    elif user.role == 'supervisor':
        return render(request, 'accounts/dashboard_supervisor.html')

    elif user.role == 'sales_staff':
        return render(request, 'accounts/dashboard_sales.html')

    else:
        return HttpResponseForbidden("Unknown role. Contact your administrator.")


@login_required
def create_staff(request):
    """
    Owner-only: Create a new staff member tied to the owner's company.
    Managers, Supervisors, and Sales Staff are explicitly denied.
    """
    user = request.user
    if user.role != 'owner':
        return HttpResponseForbidden("Only owners can create or manage staff accounts.")

    if request.method == 'POST':
        form = StaffCreationForm(request.POST)
        if form.is_valid():
            staff_user = form.save(commit=False)
            staff_user.company = user.company
            staff_user.save()
            messages.success(request, f'Staff account "{staff_user.username}" created successfully.')
            return redirect('dashboard')
    else:
        form = StaffCreationForm()

    return render(request, 'accounts/create_staff.html', {'form': form})