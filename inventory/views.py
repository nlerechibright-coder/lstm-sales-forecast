from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Avg, Count, Q, F
from django.contrib import messages
from django.http import JsonResponse, HttpResponseForbidden
from django.views.decorators.http import require_POST
from .models import Product, InventoryCategory, PaymentMethod
from .forms import ProductForm, InventoryCategoryForm, PaymentMethodForm
from sales.models import Sales
from datetime import date, timedelta


def _check_inventory_permission(user):
    """Only Owner and Manager can access inventory management."""
    return user.role in ['owner', 'manager']


@login_required
def inventory_dashboard(request):
    """
    Inventory overview dashboard with key metrics.
    Restricted to Owner and Manager roles.
    """
    if not _check_inventory_permission(request.user):
        return HttpResponseForbidden("Access denied. Only Owners and Managers can access Inventory.")

    company = request.user.company

    products = Product.objects.filter(company=company)
    total_products = products.count()
    total_stock = products.aggregate(total=Sum('current_stock'))['total'] or 0

    # Low stock alerts
    low_stock_products = products.filter(current_stock__lte=F('reorder_level'))
    low_stock_count = low_stock_products.count()

    # Out of stock
    out_of_stock_count = products.filter(current_stock=0).count()

    # Total inventory value
    total_value = sum(
        (p.current_stock * p.base_price) for p in products
    )

    # Recent activity (last 7 days of sales)
    seven_days_ago = date.today() - timedelta(days=7)
    recent_sales = Sales.objects.filter(
        company=company,
        date__gte=seven_days_ago
    )
    recent_sales_total = recent_sales.aggregate(
        total_qty=Sum('sales_quantity'),
        total_amount=Sum('sales_amount')
    )

    # Top selling products (last 30 days)
    thirty_days_ago = date.today() - timedelta(days=30)
    top_products = Sales.objects.filter(
        company=company,
        date__gte=thirty_days_ago,
        product__isnull=False
    ).values(
        'product__name', 'product__sku'
    ).annotate(
        total_sold=Sum('sales_quantity')
    ).order_by('-total_sold')[:5]

    context = {
        'total_products': total_products,
        'total_stock': total_stock,
        'low_stock_count': low_stock_count,
        'out_of_stock_count': out_of_stock_count,
        'total_value': total_value,
        'recent_sales_qty': recent_sales_total['total_qty'] or 0,
        'recent_sales_amount': recent_sales_total['total_amount'] or 0,
        'top_products': top_products,
        'low_stock_products': low_stock_products[:5],
    }

    return render(request, 'inventory/dashboard.html', context)


@login_required
def list_products(request):
    """List all products with search and filtering. Restricted to Owner/Manager."""
    if not _check_inventory_permission(request.user):
        return HttpResponseForbidden("Access denied. Only Owners and Managers can access Inventory.")

    company = request.user.company

    products = Product.objects.filter(company=company).select_related('category')

    # Search
    search_query = request.GET.get('q', '').strip()
    if search_query:
        products = products.filter(
            Q(name__icontains=search_query) |
            Q(sku__icontains=search_query) |
            Q(category__name__icontains=search_query)
        )

    # Filter by category
    category_filter = request.GET.get('category', '')
    if category_filter and category_filter != 'all':
        try:
            products = products.filter(category_id=int(category_filter))
        except (ValueError, TypeError):
            pass

    # Filter by stock status
    stock_filter = request.GET.get('stock', '')
    if stock_filter == 'low':
        products = products.filter(current_stock__lte=F('reorder_level'), current_stock__gt=0)
    elif stock_filter == 'out':
        products = products.filter(current_stock=0)
    elif stock_filter == 'ok':
        products = products.filter(current_stock__gt=F('reorder_level'))

    # Get categories for filter dropdown
    categories = InventoryCategory.objects.filter(
        company=company, is_active=True
    ).order_by('name')

    context = {
        'products': products.order_by('name'),
        'search_query': search_query,
        'category_filter': category_filter,
        'stock_filter': stock_filter,
        'categories': categories,
    }

    return render(request, 'inventory/product_list.html', context)


@login_required
def add_product(request):
    """Add a new product. Restricted to Owner/Manager."""
    if not _check_inventory_permission(request.user):
        return HttpResponseForbidden("Access denied. Only Owners and Managers can manage products.")

    company = request.user.company
    
    if request.method == 'POST':
        form = ProductForm(request.POST, company=company)
        if form.is_valid():
            product = form.save(commit=False)
            product.company = company
            
            # Handle auto SKU generation
            if product.auto_generate_sku and not product.sku:
                product.save()  # save() will auto-generate SKU
            else:
                product.save()
            
            messages.success(request, f'Product "{product.name}" added successfully.')
            return redirect('list_products')
    else:
        form = ProductForm(company=company)

    categories_exist = InventoryCategory.objects.filter(company=company, is_active=True).exists()
    return render(request, 'inventory/add_product.html', {
        'form': form,
        'categories_exist': categories_exist,
    })


@login_required
def product_detail(request, product_id):
    """Detailed view of a single product. Restricted to Owner/Manager."""
    if not _check_inventory_permission(request.user):
        return HttpResponseForbidden("Access denied. Only Owners and Managers can access Inventory.")

    company = request.user.company

    product = get_object_or_404(
        Product.objects.select_related('category'),
        id=product_id,
        company=company
    )

    # Sales history for this product
    sales_history = Sales.objects.filter(
        company=company,
        product=product
    ).order_by('-date')[:30]

    total_sold = sum(s.sales_quantity for s in sales_history)
    total_revenue = sum(
        (s.sales_amount or 0) for s in sales_history
    )
    avg_daily = total_sold / max(len(sales_history), 1)

    # Stock status
    stock_status = 'healthy'
    if product.current_stock == 0:
        stock_status = 'out'
    elif product.current_stock <= product.reorder_level:
        stock_status = 'low'

    # Days of stock remaining (simple estimate)
    days_remaining = None
    if avg_daily > 0:
        days_remaining = int(product.current_stock / avg_daily)

    context = {
        'product': product,
        'sales_history': sales_history,
        'total_sold': total_sold,
        'total_revenue': total_revenue,
        'avg_daily': round(avg_daily, 2),
        'stock_status': stock_status,
        'days_remaining': days_remaining,
    }

    return render(request, 'inventory/product_detail.html', context)


@login_required
def inventory_alerts(request):
    """View all inventory alerts. Restricted to Owner/Manager."""
    if not _check_inventory_permission(request.user):
        return HttpResponseForbidden("Access denied. Only Owners and Managers can access Inventory.")

    company = request.user.company

    products = Product.objects.filter(company=company)

    out_of_stock = products.filter(current_stock=0).order_by('name')
    low_stock = products.filter(
        current_stock__gt=0,
        current_stock__lte=F('reorder_level')
    ).order_by('current_stock')

    # Products with no recent sales (potential dead stock)
    thirty_days_ago = date.today() - timedelta(days=30)
    active_product_ids = Sales.objects.filter(
        company=company,
        date__gte=thirty_days_ago,
        product__isnull=False
    ).values_list('product_id', flat=True).distinct()

    dead_stock = products.exclude(id__in=active_product_ids).filter(current_stock__gt=0)

    context = {
        'out_of_stock': out_of_stock,
        'low_stock': low_stock,
        'dead_stock': dead_stock,
        'out_of_stock_count': out_of_stock.count(),
        'low_stock_count': low_stock.count(),
        'dead_stock_count': dead_stock.count(),
    }

    return render(request, 'inventory/alerts.html', context)


@login_required
def inventory_settings(request):
    """Inventory settings page. Restricted to Owner/Manager."""
    if not _check_inventory_permission(request.user):
        return HttpResponseForbidden("Access denied. Only Owners and Managers can access Inventory Settings.")

    company = request.user.company
    
    categories = InventoryCategory.objects.filter(company=company).order_by('name')
    payment_methods = PaymentMethod.objects.filter(company=company).order_by('name')
    
    context = {
        'categories': categories,
        'payment_methods': payment_methods,
    }
    
    return render(request, 'inventory/settings.html', context)


# Category Management Views

@login_required
def category_list(request):
    """List all inventory categories. Restricted to Owner/Manager."""
    if not _check_inventory_permission(request.user):
        return HttpResponseForbidden("Access denied.")

    company = request.user.company
    categories = InventoryCategory.objects.filter(company=company).order_by('name')
    
    context = {
        'categories': categories,
    }
    return render(request, 'inventory/category_list.html', context)


@login_required
def category_add(request):
    """Add a new inventory category. Restricted to Owner/Manager."""
    if not _check_inventory_permission(request.user):
        return HttpResponseForbidden("Access denied.")

    if request.method == 'POST':
        form = InventoryCategoryForm(request.POST)
        if form.is_valid():
            category = form.save(commit=False)
            category.company = request.user.company
            category.save()
            messages.success(request, f'Category "{category.name}" added successfully.')
            return redirect('category_list')
    else:
        form = InventoryCategoryForm()
    
    return render(request, 'inventory/category_form.html', {'form': form, 'action': 'Add'})


@login_required
def category_edit(request, category_id):
    """Edit an existing inventory category. Restricted to Owner/Manager."""
    if not _check_inventory_permission(request.user):
        return HttpResponseForbidden("Access denied.")

    company = request.user.company
    category = get_object_or_404(InventoryCategory, id=category_id, company=company)
    
    if request.method == 'POST':
        form = InventoryCategoryForm(request.POST, instance=category)
        if form.is_valid():
            form.save()
            messages.success(request, f'Category "{category.name}" updated successfully.')
            return redirect('category_list')
    else:
        form = InventoryCategoryForm(instance=category)
    
    return render(request, 'inventory/category_form.html', {'form': form, 'action': 'Edit'})


@login_required
@require_POST
def category_delete(request, category_id):
    """Delete an inventory category. Restricted to Owner/Manager."""
    if not _check_inventory_permission(request.user):
        return HttpResponseForbidden("Access denied.")

    company = request.user.company
    category = get_object_or_404(InventoryCategory, id=category_id, company=company)
    
    # Check if category has products
    if category.products.exists():
        return JsonResponse({
            'success': False,
            'error': f'Cannot delete category "{category.name}" because it has {category.products.count()} products.'
        })
    
    category.delete()
    return JsonResponse({
        'success': True,
        'message': f'Category "{category.name}" deleted successfully.'
    })


# Payment Method Management Views

@login_required
def payment_method_list(request):
    """List all payment methods. Restricted to Owner/Manager."""
    if not _check_inventory_permission(request.user):
        return HttpResponseForbidden("Access denied.")

    company = request.user.company
    payment_methods = PaymentMethod.objects.filter(company=company).order_by('name')
    
    context = {
        'payment_methods': payment_methods,
    }
    return render(request, 'inventory/payment_method_list.html', context)


@login_required
def payment_method_add(request):
    """Add a new payment method. Restricted to Owner/Manager."""
    if not _check_inventory_permission(request.user):
        return HttpResponseForbidden("Access denied.")

    if request.method == 'POST':
        form = PaymentMethodForm(request.POST)
        if form.is_valid():
            payment_method = form.save(commit=False)
            payment_method.company = request.user.company
            payment_method.save()
            messages.success(request, f'Payment method "{payment_method.name}" added successfully.')
            return redirect('payment_method_list')
    else:
        form = PaymentMethodForm()
    
    return render(request, 'inventory/payment_method_form.html', {'form': form, 'action': 'Add'})


@login_required
def payment_method_edit(request, method_id):
    """Edit an existing payment method. Restricted to Owner/Manager."""
    if not _check_inventory_permission(request.user):
        return HttpResponseForbidden("Access denied.")

    company = request.user.company
    payment_method = get_object_or_404(PaymentMethod, id=method_id, company=company)
    
    if request.method == 'POST':
        form = PaymentMethodForm(request.POST, instance=payment_method)
        if form.is_valid():
            form.save()
            messages.success(request, f'Payment method "{payment_method.name}" updated successfully.')
            return redirect('payment_method_list')
    else:
        form = PaymentMethodForm(instance=payment_method)
    
    return render(request, 'inventory/payment_method_form.html', {'form': form, 'action': 'Edit', 'payment_method': payment_method})


@login_required
@require_POST
def payment_method_delete(request, method_id):
    """Delete a payment method. Restricted to Owner/Manager."""
    if not _check_inventory_permission(request.user):
        return HttpResponseForbidden("Access denied.")

    company = request.user.company
    payment_method = get_object_or_404(PaymentMethod, id=method_id, company=company)
    
    payment_method.delete()
    return JsonResponse({
        'success': True,
        'message': f'Payment method "{payment_method.name}" deleted successfully.'
    })