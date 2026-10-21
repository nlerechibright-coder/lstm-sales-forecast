from typing import List, Dict, Any, Optional
from decimal import Decimal
from accounts.models import Company
from inventory.models import Product
from promotions.models import Promotion
from sales.models import Sales, DataImport


def import_valid_rows(
    valid_rows: List[Dict[str, Any]],
    company_id: int,
    upload_job_id: int
) -> Dict[str, Any]:
    """
    Import validated rows into the Sales table.
    Note: This function does NOT wrap in transaction.atomic because
    DataImport records are already created outside this call.
    """
    company = Company.objects.get(id=company_id)
    imported_count = 0
    skipped_count = 0
    errors = []

    for row in valid_rows:
        try:
            _import_single_row(row, company, upload_job_id)
            imported_count += 1
        except Exception as e:
            skipped_count += 1
            errors.append({
                'row': row,
                'error': str(e)
            })

    return {
        'imported': imported_count,
        'skipped': skipped_count,
        'errors': errors
    }


def _import_single_row(
    row: Dict[str, Any],
    company: Company,
    upload_job_id: int
) -> Sales:
    """Import a single validated row into the Sales table."""
    product = _resolve_product(company, row)
    promotion = _resolve_promotion(company, row.get('date'))

    data_import = DataImport.objects.filter(
        upload_job_id=upload_job_id,
        status='VALIDATED',
        normalized_data__date=row['date'].isoformat()
    ).first()

    sales = Sales.objects.create(
        company=company,
        product=product,
        date=row['date'],
        sales_quantity=row['sales_quantity'],
        sales_amount=row.get('sales_amount'),
        discount=row.get('discount'),
        promotion=promotion,
        source_import=data_import
    )

    return sales


def _resolve_product(
    company: Company,
    row: Dict[str, Any]
) -> Optional[Product]:
    """Try to find an existing Product by name or SKU."""
    product_name = row.get('product_name')
    sku = row.get('sku')

    if sku:
        try:
            return Product.objects.get(company=company, sku__iexact=sku)
        except Product.DoesNotExist:
            pass

    if product_name:
        try:
            return Product.objects.get(company=company, name__iexact=product_name)
        except Product.DoesNotExist:
            pass

    return None


def _resolve_promotion(
    company: Company,
    sale_date: Any
) -> Optional[Promotion]:
    """Find an active promotion that covers the given sale date."""
    if not sale_date:
        return None

    try:
        return Promotion.objects.get(
            company=company,
            start_date__lte=sale_date,
            end_date__gte=sale_date
        )
    except (Promotion.DoesNotExist, Promotion.MultipleObjectsReturned):
        return None


def rollback_import(upload_job_id: int) -> int:
    """Rollback all Sales records imported from a specific UploadJob."""
    count, _ = Sales.objects.filter(
        source_import__upload_job_id=upload_job_id
    ).delete()

    DataImport.objects.filter(upload_job_id=upload_job_id).update(status='SKIPPED')

    return count