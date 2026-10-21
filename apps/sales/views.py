from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseForbidden
from django.views.decorators.http import require_POST
from django.db import transaction
from django.db.models import Q, Sum
from django.core.paginator import Paginator
from django.contrib import messages
from .models import Customer, SalesTransaction, SalesTransactionItem, Sales
from .forms import CustomerForm, SalesTransactionForm, SalesTransactionItemForm
from inventory.models import Product
from datetime import date
import json


# Helper to check RBAC (Owner or Manager only)
def _check_customer_permission(user):
    return user.role in ['owner', 'manager']


def _check_sales_view_permission(user):
    """Owner, Manager, and Supervisor can view transactions. Sales Staff cannot."""
    return user.role in ['owner', 'manager', 'supervisor']


@login_required
def sales_entry(request):
    """
    Main sales entry page. Allows recording a new sales transaction.
    Accessible by Owner, Manager, and Sales Staff.
    """
    # Sales Staff, Manager, and Owner can all record sales
    if request.user.role not in ['owner', 'manager', 'sales_staff']:
        return HttpResponseForbidden("Access denied. You do not have permission to record sales.")

    company = request.user.company

    if request.method == 'POST':
        transaction_form = SalesTransactionForm(request.POST, company=company)
        
        if transaction_form.is_valid():
            try:
                with transaction.atomic():
                    # Create transaction header
                    sales_transaction = transaction_form.save(commit=False)
                    sales_transaction.company = company
                    sales_transaction.created_by = request.user
                    sales_transaction.save()

                    # Process line items from POST data
                    products = request.POST.getlist('product[]')
                    quantities = request.POST.getlist('quantity[]')
                    unit_prices = request.POST.getlist('unit_price[]')
                    discounts = request.POST.getlist('discount[]')

                    total_amount = 0
                    total_discount = 0

                    for i in range(len(products)):
                        if not products[i]:
                            continue

                        product = Product.objects.get(id=products[i], company=company)
                        quantity = int(quantities[i])
                        unit_price = float(unit_prices[i])
                        discount = float(discounts[i]) if discounts[i] else 0.0

                        # Check stock availability
                        if product.current_stock < quantity:
                            raise ValueError(f"Insufficient stock for {product.name}. Available: {product.current_stock}")

                        # Create transaction item
                        item = SalesTransactionItem.objects.create(
                            transaction=sales_transaction,
                            product=product,
                            quantity=quantity,
                            unit_price=unit_price,
                            discount=discount
                        )

                        # Deduct inventory
                        product.current_stock -= quantity
                        product.save()

                        # Create Sales record for forecasting compatibility
                        Sales.objects.create(
                            company=company,
                            product=product,
                            date=date.today(),
                            sales_quantity=quantity,
                            sales_amount=item.subtotal + discount,
                            discount=discount,
                            source_transaction=sales_transaction
                        )

                        total_amount += float(item.subtotal)
                        total_discount += discount

                    # Update transaction totals
                    sales_transaction.total_amount = total_amount
                    sales_transaction.total_discount = total_discount
                    sales_transaction.save()

                return redirect('transaction_detail', transaction_id=sales_transaction.id)

            except ValueError as e:
                transaction_form.add_error(None, str(e))
    else:
        transaction_form = SalesTransactionForm(company=company)

    # Get products for JavaScript
    products = Product.objects.filter(company=company).select_related('category')
    products_data = [
        {
            'id': p.id,
            'name': p.name,
            'sku': p.sku,
            'category': p.category.name if p.category else None,
            'price': float(p.base_price),
            'stock': p.current_stock
        }
        for p in products
    ]

    context = {
        'transaction_form': transaction_form,
        'products_json': json.dumps(products_data),
    }

    return render(request, 'sales/sales_entry.html', context)


@login_required
def customer_list(request):
    """List all customers for the company. Restricted to Owner/Manager."""
    if not _check_customer_permission(request.user):
        return HttpResponseForbidden("Access denied. Owners and Managers only.")

    company = request.user.company
    customers = Customer.objects.filter(company=company)

    # Search
    search_query = request.GET.get('q', '').strip()
    if search_query:
        customers = customers.filter(
            Q(name__icontains=search_query) |
            Q(phone__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(city__icontains=search_query)
        )

    # Filter by active status (Robust handling)
    status_filter = request.GET.get('status', '').strip().lower()
    if status_filter == 'active':
        customers = customers.filter(is_active=True)
    elif status_filter == 'inactive':
        customers = customers.filter(is_active=False)

    # Pagination
    paginator = Paginator(customers, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'search_query': search_query,
        'status_filter': status_filter,
        'total_customers': customers.count(),
    }

    return render(request, 'sales/customer_list.html', context)


@login_required
def customer_add(request):
    """Add a new customer. Restricted to Owner/Manager."""
    if not _check_customer_permission(request.user):
        return HttpResponseForbidden("Access denied. Owners and Managers only.")

    if request.method == 'POST':
        form = CustomerForm(request.POST)
        if form.is_valid():
            customer = form.save(commit=False)
            customer.company = request.user.company
            customer.save()
            messages.success(request, f'Customer "{customer.name}" added successfully.')
            return redirect('customer_list')
    else:
        form = CustomerForm()

    return render(request, 'sales/customer_form.html', {'form': form, 'action': 'Add'})


@login_required
def customer_edit(request, customer_id):
    """Edit an existing customer. Restricted to Owner/Manager."""
    if not _check_customer_permission(request.user):
        return HttpResponseForbidden("Access denied. Owners and Managers only.")

    company = request.user.company
    customer = get_object_or_404(Customer, id=customer_id, company=company)

    if request.method == 'POST':
        form = CustomerForm(request.POST, instance=customer)
        if form.is_valid():
            form.save()
            messages.success(request, f'Customer "{customer.name}" updated successfully.')
            return redirect('customer_list')
    else:
        form = CustomerForm(instance=customer)

    return render(request, 'sales/customer_form.html', {'form': form, 'action': 'Edit', 'customer': customer})


@login_required
def customer_detail(request, customer_id):
    """View customer details. Restricted to Owner/Manager."""
    if not _check_customer_permission(request.user):
        return HttpResponseForbidden("Access denied. Owners and Managers only.")

    company = request.user.company
    customer = get_object_or_404(Customer, id=customer_id, company=company)

    # Get customer's transaction history
    transactions = SalesTransaction.objects.filter(
        company=company,
        customer=customer
    ).order_by('-transaction_date')[:10]

    context = {
        'customer': customer,
        'transactions': transactions,
    }
    return render(request, 'sales/customer_detail.html', context)


@login_required
@require_POST
def customer_delete(request, customer_id):
    """Soft delete (deactivate) a customer. Restricted to Owner/Manager."""
    if not _check_customer_permission(request.user):
        return HttpResponseForbidden("Access denied. Owners and Managers only.")

    company = request.user.company
    customer = get_object_or_404(Customer, id=customer_id, company=company)
    
    # Soft delete (set to inactive)
    customer.is_active = False
    customer.save()
    
    return JsonResponse({
        'success': True,
        'message': f'Customer "{customer.name}" has been deactivated.'
    })


@login_required
def transaction_list(request):
    """List all sales transactions. Restricted to Owner, Manager, Supervisor."""
    if not _check_sales_view_permission(request.user):
        return HttpResponseForbidden("Access denied. You do not have permission to view transactions.")

    company = request.user.company
    transactions = SalesTransaction.objects.filter(company=company).select_related('customer', 'payment_method')

    # Date range filter
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    if date_from:
        try:
            transactions = transactions.filter(transaction_date__date__gte=date_from)
        except ValueError:
            pass
    if date_to:
        try:
            transactions = transactions.filter(transaction_date__date__lte=date_to)
        except ValueError:
            pass

    # Pagination
    paginator = Paginator(transactions, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'date_from': date_from,
        'date_to': date_to,
        'total_transactions': transactions.count(),
    }

    return render(request, 'sales/transaction_list.html', context)


@login_required
def transaction_detail(request, transaction_id):
    """View details of a specific transaction. Restricted to Owner, Manager, Supervisor."""
    if not _check_sales_view_permission(request.user):
        return HttpResponseForbidden("Access denied. You do not have permission to view transactions.")

    company = request.user.company
    transaction = get_object_or_404(
        SalesTransaction.objects.select_related('customer', 'payment_method', 'created_by'),
        id=transaction_id,
        company=company
    )

    items = transaction.items.select_related('product', 'product__category').all()

    context = {
        'transaction': transaction,
        'items': items,
    }

    return render(request, 'sales/transaction_detail.html', context)


@login_required
def product_search(request):
    """
    AJAX endpoint for searching products.
    Accessible by Owner, Manager, and Sales Staff (needed for sales entry).
    """
    if request.user.role not in ['owner', 'manager', 'sales_staff']:
        return JsonResponse({'products': [], 'error': 'Access denied'}, status=403)

    company = request.user.company
    query = request.GET.get('q', '').strip()

    if not query:
        return JsonResponse({'products': []})

    # Fixed: Q objects must come before keyword arguments
    products = Product.objects.filter(
        Q(name__icontains=query) | Q(sku__icontains=query),
        company=company
    ).select_related('category')[:10]

    products_data = [
        {
            'id': p.id,
            'name': p.name,
            'sku': p.sku,
            'category': p.category.name if p.category else None,
            'price': float(p.base_price),
            'stock': p.current_stock
        }
        for p in products
    ]

    return JsonResponse({'products': products_data})