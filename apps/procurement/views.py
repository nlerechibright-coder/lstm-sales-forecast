from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseForbidden
from django.views.decorators.http import require_POST
from django.db.models import Sum, Count, Avg, Q
from django.core.paginator import Paginator
from django.contrib import messages
from django.db import transaction
from .models import Supplier, PurchaseOrder, PurchaseOrderItem, SupplierInvoice, PurchaseHistory
from .forms import (
    SupplierForm, PurchaseOrderForm, PurchaseOrderItemForm,
    SupplierInvoiceForm, BulkInvoiceUploadForm
)
from .services.invoice_extractor import InvoiceExtractor
from inventory.models import Product
from datetime import datetime, date
import json
import logging

logger = logging.getLogger(__name__)


def _check_procurement_permission(user):
    """Only Owner and Manager can access procurement."""
    return user.role in ['owner', 'manager']


# ============================================================================
# DASHBOARD
# ============================================================================

@login_required
def procurement_dashboard(request):
    """Procurement dashboard with KPIs."""
    if not _check_procurement_permission(request.user):
        return HttpResponseForbidden("Access denied. Only Owners and Managers can access Procurement.")

    company = request.user.company

    total_suppliers = Supplier.objects.filter(company=company, status='active').count()
    
    total_orders = PurchaseHistory.objects.filter(company=company).count()
    pending_orders = PurchaseOrder.objects.filter(company=company, status__in=['pending', 'ordered']).count()
    
    total_spent = PurchaseHistory.objects.filter(company=company).aggregate(
        total=Sum('total_cost')
    )['total'] or 0

    recent_orders = PurchaseHistory.objects.filter(company=company).select_related(
        'supplier', 'product'
    ).order_by('-received_date')[:5]

    # FIX: Renamed annotation from 'total_spent' to 'history_total_spent' 
    # to prevent conflict with the Supplier model's existing 'total_spent' field.
    top_suppliers = Supplier.objects.filter(company=company).annotate(
        order_count=Count('history_records'),
        history_total_spent=Sum('history_records__total_cost')
    ).order_by('-history_total_spent')[:5]

    products_with_cost = Product.objects.filter(company=company, cost_price__isnull=False)
    inventory_value = sum(
        float(p.current_stock) * float(p.cost_price) for p in products_with_cost
    )

    context = {
        'total_suppliers': total_suppliers,
        'total_orders': total_orders,
        'pending_orders': pending_orders,
        'total_spent': total_spent,
        'recent_orders': recent_orders,
        'top_suppliers': top_suppliers,
        'inventory_value': inventory_value,
    }

    return render(request, 'procurement/dashboard.html', context)


# ============================================================================
# SUPPLIER MANAGEMENT
# ============================================================================

@login_required
def supplier_list(request):
    if not _check_procurement_permission(request.user):
        return HttpResponseForbidden("Access denied.")

    company = request.user.company
    suppliers = Supplier.objects.filter(company=company)

    query = request.GET.get('q', '').strip()
    if query:
        suppliers = suppliers.filter(
            Q(name__icontains=query) |
            Q(contact_person__icontains=query) |
            Q(email__icontains=query)
        )

    status_filter = request.GET.get('status', '')
    if status_filter:
        suppliers = suppliers.filter(status=status_filter)

    paginator = Paginator(suppliers, 20)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    context = {
        'page_obj': page_obj,
        'query': query,
        'status_filter': status_filter,
        'total_suppliers': suppliers.count(),
    }

    return render(request, 'procurement/supplier_list.html', context)


@login_required
def supplier_add(request):
    if not _check_procurement_permission(request.user):
        return HttpResponseForbidden("Access denied.")

    if request.method == 'POST':
        form = SupplierForm(request.POST)
        if form.is_valid():
            supplier = form.save(commit=False)
            supplier.company = request.user.company
            supplier.created_by = request.user
            supplier.save()
            messages.success(request, f'Supplier "{supplier.name}" added successfully.')
            return redirect('supplier_list')
    else:
        form = SupplierForm()

    return render(request, 'procurement/supplier_form.html', {'form': form, 'action': 'Add'})


@login_required
def supplier_edit(request, supplier_id):
    if not _check_procurement_permission(request.user):
        return HttpResponseForbidden("Access denied.")

    company = request.user.company
    supplier = get_object_or_404(Supplier, id=supplier_id, company=company)

    if request.method == 'POST':
        form = SupplierForm(request.POST, instance=supplier)
        if form.is_valid():
            form.save()
            messages.success(request, f'Supplier "{supplier.name}" updated successfully.')
            return redirect('supplier_list')
    else:
        form = SupplierForm(instance=supplier)

    return render(request, 'procurement/supplier_form.html', {'form': form, 'action': 'Edit', 'supplier': supplier})


@login_required
def supplier_detail(request, supplier_id):
    if not _check_procurement_permission(request.user):
        return HttpResponseForbidden("Access denied.")

    company = request.user.company
    supplier = get_object_or_404(Supplier, id=supplier_id, company=company)
    orders = supplier.purchase_orders.order_by('-order_date')[:10]
    invoices = supplier.invoices.order_by('-invoice_date')[:10]
    history = supplier.history_records.order_by('-received_date')[:10]

    context = {
        'supplier': supplier,
        'orders': orders,
        'invoices': invoices,
        'history': history,
    }

    return render(request, 'procurement/supplier_detail.html', context)


# ============================================================================
# PURCHASE ORDERS
# ============================================================================

@login_required
def purchase_order_list(request):
    if not _check_procurement_permission(request.user):
        return HttpResponseForbidden("Access denied.")

    company = request.user.company
    orders = PurchaseOrder.objects.filter(company=company).select_related('supplier')

    query = request.GET.get('q', '').strip()
    if query:
        orders = orders.filter(
            Q(order_number__icontains=query) |
            Q(supplier__name__icontains=query)
        )

    status_filter = request.GET.get('status', '')
    if status_filter:
        orders = orders.filter(status=status_filter)

    paginator = Paginator(orders, 20)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    context = {
        'page_obj': page_obj,
        'query': query,
        'status_filter': status_filter,
        'total_orders': orders.count(),
    }

    return render(request, 'procurement/purchase_order_list.html', context)


@login_required
def purchase_order_add(request):
    if not _check_procurement_permission(request.user):
        return HttpResponseForbidden("Access denied.")

    company = request.user.company

    if request.method == 'POST':
        form = PurchaseOrderForm(request.POST)
        if form.is_valid():
            purchase_order = form.save(commit=False)
            purchase_order.company = company
            purchase_order.created_by = request.user
            purchase_order.save()

            products = request.POST.getlist('product[]')
            quantities = request.POST.getlist('quantity[]')
            unit_costs = request.POST.getlist('unit_cost[]')

            for i in range(len(products)):
                if products[i] and quantities[i] and unit_costs[i]:
                    PurchaseOrderItem.objects.create(
                        purchase_order=purchase_order,
                        product_id=products[i],
                        quantity_ordered=int(quantities[i]),
                        unit_cost=float(unit_costs[i])
                    )

            purchase_order.save()

            messages.success(request, f'Purchase Order {purchase_order.order_number} created successfully.')
            return redirect('purchase_order_detail', order_id=purchase_order.id)
    else:
        form = PurchaseOrderForm()

    products = Product.objects.filter(company=company)
    suppliers = Supplier.objects.filter(company=company, status='active')

    context = {
        'form': form,
        'products': products,
        'suppliers': suppliers,
    }

    return render(request, 'procurement/purchase_order_form.html', context)


@login_required
def purchase_order_detail(request, order_id):
    if not _check_procurement_permission(request.user):
        return HttpResponseForbidden("Access denied.")

    company = request.user.company
    order = get_object_or_404(
        PurchaseOrder.objects.select_related('supplier', 'created_by'),
        id=order_id,
        company=company
    )

    items = order.items.select_related('product').all()
    invoices = order.invoices.all()

    context = {
        'order': order,
        'items': items,
        'invoices': invoices,
    }

    return render(request, 'procurement/purchase_order_detail.html', context)


@login_required
@require_POST
def receive_purchase_order(request, order_id):
    """Mark purchase order as received and update inventory."""
    if not _check_procurement_permission(request.user):
        return HttpResponseForbidden("Access denied.")

    company = request.user.company
    order = get_object_or_404(PurchaseOrder, id=order_id, company=company)

    if order.status == 'received':
        messages.warning(request, 'This order has already been received.')
        return redirect('purchase_order_detail', order_id=order.id)

    try:
        with transaction.atomic():
            for item in order.items.all():
                product = item.product
                product.current_stock += item.quantity_ordered
                product.cost_price = item.unit_cost
                product.save()

                item.quantity_received = item.quantity_ordered
                item.save()

                PurchaseHistory.objects.create(
                    company=company,
                    purchase_order=order,
                    supplier=order.supplier,
                    product=product,
                    quantity=item.quantity_ordered,
                    unit_cost=item.unit_cost,
                    total_cost=item.total_cost,
                    purchase_date=order.order_date,
                    received_date=date.today(),
                    created_by=request.user
                )

            order.status = 'received'
            order.actual_delivery = date.today()
            order.save()

            supplier = order.supplier
            supplier.total_orders += 1
            supplier.total_spent += order.total_amount
            supplier.save()

        messages.success(request, f'Purchase Order {order.order_number} received. Inventory updated.')
        return redirect('purchase_order_detail', order_id=order.id)

    except Exception as e:
        messages.error(request, f'Error receiving order: {str(e)}')
        return redirect('purchase_order_detail', order_id=order.id)


@login_required
@require_POST
def cancel_purchase_order(request, order_id):
    if not _check_procurement_permission(request.user):
        return HttpResponseForbidden("Access denied.")

    company = request.user.company
    order = get_object_or_404(PurchaseOrder, id=order_id, company=company)

    if order.status == 'received':
        messages.error(request, 'Cannot cancel a received order.')
        return redirect('purchase_order_detail', order_id=order.id)

    order.status = 'cancelled'
    order.save()

    messages.success(request, f'Purchase Order {order.order_number} cancelled.')
    return redirect('purchase_order_detail', order_id=order.id)


# ============================================================================
# SUPPLIER INVOICES
# ============================================================================

@login_required
def invoice_list(request):
    if not _check_procurement_permission(request.user):
        return HttpResponseForbidden("Access denied.")

    company = request.user.company
    invoices = SupplierInvoice.objects.filter(company=company).select_related('supplier', 'purchase_order')

    query = request.GET.get('q', '').strip()
    if query:
        invoices = invoices.filter(
            Q(invoice_number__icontains=query) |
            Q(supplier__name__icontains=query)
        )

    status_filter = request.GET.get('status', '')
    if status_filter:
        invoices = invoices.filter(status=status_filter)

    paginator = Paginator(invoices, 20)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    context = {
        'page_obj': page_obj,
        'query': query,
        'status_filter': status_filter,
        'total_invoices': invoices.count(),
    }

    return render(request, 'procurement/invoice_list.html', context)


@login_required
def invoice_add(request):
    if not _check_procurement_permission(request.user):
        return HttpResponseForbidden("Access denied.")

    company = request.user.company

    if request.method == 'POST':
        form = SupplierInvoiceForm(request.POST, request.FILES)
        if form.is_valid():
            invoice = form.save(commit=False)
            invoice.company = company
            invoice.created_by = request.user
            invoice.save()
            messages.success(request, f'Invoice {invoice.invoice_number} added successfully.')
            return redirect('invoice_list')
    else:
        form = SupplierInvoiceForm()

    form.fields['purchase_order'].queryset = PurchaseOrder.objects.filter(company=company)
    form.fields['supplier'].queryset = Supplier.objects.filter(company=company)

    return render(request, 'procurement/invoice_form.html', {'form': form, 'action': 'Add'})


@login_required
def invoice_detail(request, invoice_id):
    if not _check_procurement_permission(request.user):
        return HttpResponseForbidden("Access denied.")

    company = request.user.company
    invoice = get_object_or_404(
        SupplierInvoice.objects.select_related('supplier', 'purchase_order'),
        id=invoice_id,
        company=company
    )

    context = {'invoice': invoice}
    return render(request, 'procurement/invoice_detail.html', context)


# ============================================================================
# BULK INVOICE UPLOAD
# ============================================================================

@login_required
def invoice_bulk_upload(request):
    """
    Upload a compiled CSV/Excel purchase report.
    Step 1: Upload and parse file.
    Step 2: Review extracted records.
    Step 3: Confirm and apply to inventory.
    """
    if not _check_procurement_permission(request.user):
        return HttpResponseForbidden("Access denied.")

    company = request.user.company

    if request.method == 'POST':
        action = request.POST.get('action', '')

        if action == 'parse':
            form = BulkInvoiceUploadForm(request.POST, request.FILES)
            if form.is_valid():
                uploaded_file = request.FILES['file']
                result = InvoiceExtractor.parse_file(uploaded_file)

                if not result['success']:
                    messages.error(request, f'Failed to parse file: {", ".join(result["errors"])}')
                    return render(request, 'procurement/invoice_bulk_upload.html', {
                        'form': BulkInvoiceUploadForm(),
                    })

                # Store extracted records in session for review
                request.session['bulk_records'] = result['records']
                request.session['bulk_meta'] = {
                    'total_rows': result['total_rows'],
                    'valid_rows': result['valid_rows'],
                    'errors': result['errors'],
                    'filename': uploaded_file.name,
                    'auto_create_suppliers': form.cleaned_data.get('auto_create_suppliers', True),
                    'auto_create_products': form.cleaned_data.get('auto_create_products', False),
                }

                return render(request, 'procurement/invoice_bulk_upload_review.html', {
                    'records': result['records'],
                    'meta': request.session['bulk_meta'],
                    'suppliers': list(Supplier.objects.filter(company=company).values_list('name', flat=True)),
                    'products': list(Product.objects.filter(company=company).values_list('name', flat=True)),
                })

        elif action == 'confirm':
            records = request.session.get('bulk_records', [])
            meta = request.session.get('bulk_meta', {})

            if not records:
                messages.error(request, 'No records to process. Please upload a file first.')
                return redirect('invoice_bulk_upload')

            auto_suppliers = meta.get('auto_create_suppliers', True)
            auto_products = meta.get('auto_create_products', False)

            created_count = 0
            updated_count = 0
            skipped_count = 0

            try:
                with transaction.atomic():
                    for record in records:
                        # Resolve or create supplier (use explicit filter+create to avoid
                        # passing lookup kwargs into create which can fail)
                        supplier = Supplier.objects.filter(
                            company=company,
                            name__iexact=record['supplier_name']
                        ).first()
                        s_created = False
                        if not supplier:
                            if auto_suppliers:
                                supplier = Supplier.objects.create(
                                    company=company,
                                    name=record['supplier_name'],
                                    status='active',
                                    created_by=request.user,
                                )
                                s_created = True
                            else:
                                skipped_count += 1
                                continue

                        # =====================================================================
                        # ROOT CAUSE FIX: Intelligent Product Resolution
                        # =====================================================================
                        product = Product.objects.filter(
                            company=company,
                            name__iexact=record['product_name']
                        ).first()

                        # Fallback: Intelligent substring matching
                        if not product:
                            rec_name_lower = record['product_name'].lower().strip()
                            # Search through company products for a partial match
                            for p in Product.objects.filter(company=company):
                                p_name_lower = p.name.lower().strip()
                                # Match if one name contains the other (minimum 4 chars to avoid false positives)
                                if len(p_name_lower) >= 4 and len(rec_name_lower) >= 4:
                                    if p_name_lower in rec_name_lower or rec_name_lower in p_name_lower:
                                        product = p
                                        logger.info(f"Intelligent match: '{record['product_name']}' -> '{p.name}'")
                                        break

                        if not product:
                            if auto_products:
                                product = Product.objects.create(
                                    company=company,
                                    name=record['product_name'],
                                    base_price=record['unit_cost'] * 1.3,  # 30% markup default
                                    cost_price=record['unit_cost'],
                                    current_stock=record['quantity'],
                                )
                                created_count += 1
                            else:
                                skipped_count += 1
                                continue
                        else:
                            # Update stock and cost price
                            product.current_stock += record['quantity']
                            product.cost_price = record['unit_cost']
                            product.save()
                            updated_count += 1

                        # Create purchase history
                        PurchaseHistory.objects.create(
                            company=company,
                            supplier=supplier,
                            product=product,
                            quantity=record['quantity'],
                            unit_cost=record['unit_cost'],
                            total_cost=record['total_cost'],
                            purchase_date=record.get('purchase_date', date.today()),
                            received_date=date.today(),
                            created_by=request.user
                        )

                # Clear session
                request.session.pop('bulk_records', None)
                request.session.pop('bulk_meta', None)

                messages.success(
                    request,
                    f'Bulk import complete: {updated_count} products updated, '
                    f'{created_count} products created, {skipped_count} skipped.'
                )
                return redirect('purchase_history')

            except Exception as e:
                logger.error(f"Error processing bulk records: {str(e)}", exc_info=True)
                messages.error(request, f'Error processing records: {str(e)}')
                return redirect('invoice_bulk_upload')

    form = BulkInvoiceUploadForm()
    return render(request, 'procurement/invoice_bulk_upload.html', {'form': form})


# ============================================================================
# PURCHASE HISTORY
# ============================================================================

@login_required
def purchase_history(request):
    if not _check_procurement_permission(request.user):
        return HttpResponseForbidden("Access denied.")

    company = request.user.company
    history = PurchaseHistory.objects.filter(company=company).select_related('supplier', 'product')

    query = request.GET.get('q', '').strip()
    if query:
        history = history.filter(
            Q(product__name__icontains=query) |
            Q(supplier__name__icontains=query)
        )

    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    if date_from:
        try:
            history = history.filter(purchase_date__gte=datetime.strptime(date_from, '%Y-%m-%d').date())
        except ValueError:
            pass
    if date_to:
        try:
            history = history.filter(purchase_date__lte=datetime.strptime(date_to, '%Y-%m-%d').date())
        except ValueError:
            pass

    paginator = Paginator(history, 20)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    context = {
        'page_obj': page_obj,
        'query': query,
        'date_from': date_from,
        'date_to': date_to,
        'total_records': history.count(),
    }

    return render(request, 'procurement/purchase_history.html', context)