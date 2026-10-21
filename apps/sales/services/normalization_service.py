import pandas as pd
import json
from datetime import datetime, date
from decimal import Decimal, InvalidOperation
from typing import List, Dict, Any, Tuple
from django.db import transaction
from django.db import models as django_models
from sales.models import DataImport, Sales


def _json_serializable(obj: Any) -> Any:
    """Convert objects that are not JSON serializable into serializable types."""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, float):
        if pd.isna(obj):
            return None
        return obj
    if hasattr(obj, "item"):
        return obj.item()
    if pd.isna(obj):
        return None
    return obj


def _make_json_safe(data: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a dict into JSON-safe types."""
    return {k: _json_serializable(v) for k, v in data.items()}


def normalize_dataframe(
    df: pd.DataFrame,
    mapped_columns: Dict[str, str],
    upload_job_id: int
) -> Tuple[List[Dict], List[Dict]]:
    """Normalize a DataFrame using confirmed column mappings."""
    # Keep re-running the same import job idempotent.
    Sales.objects.filter(source_import__upload_job_id=upload_job_id).delete()
    DataImport.objects.filter(upload_job_id=upload_job_id).delete()

    valid_rows = []
    invalid_rows = []
    field_to_header = {field: header for header, field in mapped_columns.items()}

    for idx, row in df.iterrows():
        row_number = int(idx) + 2
        raw_data = _make_json_safe(row.to_dict())

        try:
            normalized = _normalize_row(row, field_to_header)
            normalized_safe = _make_json_safe(normalized)

            DataImport.objects.create(
                upload_job_id=upload_job_id,
                row_number=row_number,
                raw_data=raw_data,
                normalized_data=normalized_safe,
                status="VALIDATED"
            )
            valid_rows.append(normalized)

        except ValueError as e:
            DataImport.objects.create(
                upload_job_id=upload_job_id,
                row_number=row_number,
                raw_data=raw_data,
                status="FAILED",
                error_message=str(e)
            )
            invalid_rows.append({
                "row_number": row_number,
                "raw_data": raw_data,
                "error": str(e)
            })

    return valid_rows, invalid_rows


def _normalize_row(row: pd.Series, field_to_header: Dict[str, str]) -> Dict[str, Any]:
    """Normalize a single DataFrame row into a clean dict."""
    normalized = {}

    date_header = field_to_header.get("date")
    if not date_header or pd.isna(row.get(date_header)):
        raise ValueError("Date is required and cannot be empty.")
    date_val = _parse_date(row[date_header])
    if date_val is None:
        raise ValueError(f"Invalid date format: '{row[date_header]}'")
    normalized["date"] = date_val

    qty_header = field_to_header.get("sales_quantity")
    if not qty_header or pd.isna(row.get(qty_header)):
        raise ValueError("Sales quantity is required and cannot be empty.")
    qty_val = _parse_integer(row[qty_header], "sales_quantity")
    if qty_val is None or qty_val < 0:
        raise ValueError(f"Invalid sales quantity: '{row[qty_header]}'")
    normalized["sales_quantity"] = qty_val

    name_header = field_to_header.get("product_name")
    if name_header and not pd.isna(row.get(name_header)):
        normalized["product_name"] = str(row[name_header]).strip()

    sku_header = field_to_header.get("sku")
    if sku_header and not pd.isna(row.get(sku_header)):
        normalized["sku"] = str(row[sku_header]).strip()

    amount_header = field_to_header.get("sales_amount")
    if amount_header and not pd.isna(row.get(amount_header)):
        amount_val = _parse_decimal(row[amount_header], "sales_amount")
        if amount_val is not None and amount_val < 0:
            raise ValueError(f"Sales amount cannot be negative: '{row[amount_header]}'")
        normalized["sales_amount"] = amount_val

    # Discount is treated as an absolute monetary amount, not a percentage.
    discount_header = field_to_header.get("discount")
    if discount_header and not pd.isna(row.get(discount_header)):
        discount_val = _parse_decimal(row[discount_header], "discount")
        if discount_val is not None and discount_val < 0:
            raise ValueError(f"Discount cannot be negative: '{row[discount_header]}'")
        normalized["discount"] = discount_val

    return normalized


def _parse_date(value: Any) -> date:
    """Parse various date formats into a Python date object."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, pd.Timestamp):
        return value.date()

    date_formats = [
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%m/%d/%Y",
        "%d-%m-%Y",
        "%m-%d-%Y",
        "%Y/%m/%d",
        "%d %b %Y",
        "%d %B %Y",
    ]

    value_str = str(value).strip()
    for fmt in date_formats:
        try:
            return datetime.strptime(value_str, fmt).date()
        except ValueError:
            continue

    try:
        parsed = pd.to_datetime(value, errors="raise")
        return parsed.date()
    except (ValueError, TypeError):
        return None


def _parse_integer(value: Any, field_name: str) -> int:
    """Parse a value into a non-negative integer."""
    try:
        if isinstance(value, (int, float)):
            return int(value)
        cleaned = str(value).replace(",", "").strip()
        return int(float(cleaned))
    except (ValueError, TypeError):
        return None


def _parse_decimal(value: Any, field_name: str) -> Decimal:
    """Parse a value into a Decimal."""
    try:
        if isinstance(value, Decimal):
            return value
        cleaned = str(value).replace(",", "").replace("$", "").replace("₦", "").strip()
        return Decimal(cleaned)
    except (InvalidOperation, ValueError, TypeError):
        return None


def get_normalization_summary(upload_job_id: int) -> Dict[str, Any]:
    """Get a summary of normalization results for an upload job."""
    stats = DataImport.objects.filter(upload_job_id=upload_job_id).aggregate(
        total=django_models.Count("id"),
        valid=django_models.Count("id", filter=django_models.Q(status="VALIDATED")),
        invalid=django_models.Count("id", filter=django_models.Q(status="FAILED"))
    )

    total = stats["total"] or 0
    valid = stats["valid"] or 0
    invalid = stats["invalid"] or 0

    return {
        "total_rows": total,
        "valid_rows": valid,
        "invalid_rows": invalid,
        "success_rate": round(valid / total * 100, 2) if total > 0 else 0.0
    }