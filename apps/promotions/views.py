from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponseForbidden
from django.views.decorators.http import require_POST
from django.db.models import Q
from .models import Promotion
from .forms import PromotionForm
from inventory.models import Product
from datetime import date


def _check_promotion_permission(user):
    """Only Owner and Manager can manage promotions."""
    return user.role in ['owner', 'manager']


@login_required
def promotion_list(request):
    """List all promotions with filtering."""
    if not _check_promotion_permission(request.user):
        return HttpResponseForbidden("Access denied. Only Owners and Managers can manage promotions.")
    
    company = request.user.company
    
    promotions = Promotion.objects.filter(company=company).prefetch_related('products')
    
    # Filter by status
    status_filter = request.GET.get('status', '')
    if status_filter == 'active':
        promotions = promotions.filter(status='active', is_active=True)
    elif status_filter == 'inactive':
        promotions = promotions.filter(status='inactive')
    elif status_filter == 'expired':
        promotions = promotions.filter(status='expired')
    
    # Search
    search_query = request.GET.get('q', '').strip()
    if search_query:
        promotions = promotions.filter(
            Q(promotion_name__icontains=search_query) |
            Q(description__icontains=search_query)
        )
    
    context = {
        'promotions': promotions,
        'status_filter': status_filter,
        'search_query': search_query,
    }
    
    return render(request, 'promotions/promotion_list.html', context)


@login_required
def promotion_create(request):
    """Create a new promotion."""
    if not _check_promotion_permission(request.user):
        return HttpResponseForbidden("Access denied.")
    
    company = request.user.company
    
    if request.method == 'POST':
        form = PromotionForm(request.POST, company=company)
        if form.is_valid():
            promotion = form.save(commit=False)
            promotion.company = company
            promotion.save()
            
            # Save products if provided
            if form.cleaned_data.get('products'):
                promotion.products.set(form.cleaned_data['products'])
            
            messages.success(request, f'Promotion "{promotion.promotion_name}" created successfully.')
            return redirect('promotion_list')
    else:
        form = PromotionForm(company=company)
    
    return render(request, 'promotions/promotion_form.html', {
        'form': form,
        'action': 'Create',
    })


@login_required
def promotion_edit(request, promotion_id):
    """Edit an existing promotion."""
    if not _check_promotion_permission(request.user):
        return HttpResponseForbidden("Access denied.")
    
    company = request.user.company
    promotion = get_object_or_404(Promotion, id=promotion_id, company=company)
    
    if request.method == 'POST':
        form = PromotionForm(request.POST, instance=promotion, company=company)
        if form.is_valid():
            promotion = form.save()
            messages.success(request, f'Promotion "{promotion.promotion_name}" updated successfully.')
            return redirect('promotion_list')
    else:
        form = PromotionForm(instance=promotion, company=company)
    
    return render(request, 'promotions/promotion_form.html', {
        'form': form,
        'action': 'Edit',
        'promotion': promotion,
    })


@login_required
@require_POST
def promotion_delete(request, promotion_id):
    """Delete a promotion."""
    if not _check_promotion_permission(request.user):
        return JsonResponse({'success': False, 'error': 'Access denied.'}, status=403)
    
    company = request.user.company
    promotion = get_object_or_404(Promotion, id=promotion_id, company=company)
    
    promotion_name = promotion.promotion_name
    promotion.delete()
    
    return JsonResponse({
        'success': True,
        'message': f'Promotion "{promotion_name}" deleted successfully.'
    })


@login_required
@require_POST
def promotion_toggle_status(request, promotion_id):
    """Toggle promotion active/inactive status."""
    if not _check_promotion_permission(request.user):
        return JsonResponse({'success': False, 'error': 'Access denied.'}, status=403)
    
    company = request.user.company
    promotion = get_object_or_404(Promotion, id=promotion_id, company=company)
    
    promotion.is_active = not promotion.is_active
    if not promotion.is_active:
        promotion.status = 'inactive'
    elif promotion.is_currently_active:
        promotion.status = 'active'
    
    promotion.save()
    
    return JsonResponse({
        'success': True,
        'message': f'Promotion {"activated" if promotion.is_active else "deactivated"} successfully.',
        'is_active': promotion.is_active,
    })