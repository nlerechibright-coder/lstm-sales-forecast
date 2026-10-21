import difflib
from typing import List, Dict, Optional
from django.db.models import F
from sales.models import ColumnMapping


# Database fields we accept for sales data import
KNOWN_FIELDS = [
    'date',
    'product_name',
    'sku',
    'sales_quantity',
    'sales_amount',
    'discount',
]

# Common synonyms companies use for each field
FIELD_SYNONYMS = {
    'date': [
        'date', 'sale date', 'transaction date', 'order date', 'purchase date',
        'dt', 'day', 'period', 'sales date', 'invoice date', 'timestamp'
    ],
    'product_name': [
        'product', 'product name', 'item', 'item name', 'description',
        'product description', 'goods', 'merchandise', 'name'
    ],
    'sku': [
        'sku', 'product code', 'item code', 'code', 'id', 'product id',
        'item id', 'stock keeping unit', 'barcode', 'upc'
    ],
    'sales_quantity': [
        'quantity', 'qty', 'sales quantity', 'units sold', 'quantity sold',
        'volume', 'sales volume', 'count', 'amount sold', 'qty sold',
        'units', 'pieces', 'number sold'
    ],
    'sales_amount': [
        'amount', 'sales amount', 'total', 'total sales', 'revenue',
        'sales revenue', 'total amount', 'gross sales', 'net sales',
        'value', 'sales value', 'turnover', 'price total'
    ],
    'discount': [
        'discount', 'discount rate', 'discount amount', 'disc',
        'price reduction', 'markdown', 'promo discount', 'deduction',
        'savings', 'coupon', 'rebate'
    ],
}


def _normalize_header(header) -> str:
    """Convert header to string, lowercase and strip whitespace."""
    return str(header).strip().lower()


def _compute_similarity(header: str, synonym: str) -> float:
    """Compute string similarity between header and synonym using difflib."""
    return difflib.SequenceMatcher(None, header, synonym).ratio()


def _find_best_field_match(header, min_confidence: float = 0.6) -> Optional[Dict]:
    """
    Find the best matching database field for a given header.
    Returns {'field_name': str, 'confidence': float} or None.
    """
    normalized = _normalize_header(header)
    best_match = None
    best_score = 0.0

    for field_name, synonyms in FIELD_SYNONYMS.items():
        for synonym in synonyms:
            score = _compute_similarity(normalized, synonym)
            if score > best_score:
                best_score = score
                best_match = field_name

    if best_match and best_score >= min_confidence:
        return {
            'field_name': best_match,
            'confidence': round(best_score, 3)
        }
    return None


def suggest_mappings(headers: List, company_id: int) -> Dict:
    """
    Suggest field mappings for a list of uploaded headers.
    """
    suggestions = {}
    company_mappings = _get_company_mappings(company_id)

    for header in headers:
        normalized = _normalize_header(header)

        # 1. Check company history first (highest priority)
        if normalized in company_mappings:
            suggestions[header] = {
                'suggested_field': company_mappings[normalized],
                'confidence': 1.0,
                'source': 'company_history'
            }
            continue

        # 2. Fall back to fuzzy matching
        match = _find_best_field_match(header)
        if match:
            suggestions[header] = {
                'suggested_field': match['field_name'],
                'confidence': match['confidence'],
                'source': 'fuzzy_match'
            }
        else:
            suggestions[header] = {
                'suggested_field': None,
                'confidence': 0.0,
                'source': 'unmatched'
            }

    return suggestions


def apply_mapping(
    company_id: int,
    header_name: str,
    field_name: str,
    confidence: float = 1.0
) -> ColumnMapping:
    """Store a confirmed column mapping for a company."""
    normalized_header = _normalize_header(header_name)

    mapping, created = ColumnMapping.objects.get_or_create(
        company_id=company_id,
        header_name=normalized_header,
        field_name=field_name,
        defaults={
            'confidence': confidence,
            'usage_count': 1,
        }
    )

    if not created:
        mapping.usage_count = F('usage_count') + 1
        mapping.confidence = confidence
        mapping.save()
        mapping.refresh_from_db()

    return mapping


def apply_mappings_bulk(
    company_id: int,
    mappings: Dict[str, str]
) -> List[ColumnMapping]:
    """Apply multiple confirmed mappings at once."""
    results = []
    for header_name, field_name in mappings.items():
        if field_name and field_name in KNOWN_FIELDS:
            mapping = apply_mapping(company_id, header_name, field_name)
            results.append(mapping)
    return results


def _get_company_mappings(company_id: int) -> Dict[str, str]:
    """Retrieve all confirmed mappings for a company as a lookup dict."""
    mappings = ColumnMapping.objects.filter(company_id=company_id)
    return {m.header_name: m.field_name for m in mappings}


def get_unmapped_headers(
    headers: List,
    company_id: int
) -> List[str]:
    """Return headers that have no mapping (fuzzy or historical) for a company."""
    suggestions = suggest_mappings(headers, company_id)
    return [
        h for h, info in suggestions.items()
        if info['suggested_field'] is None
    ]


def validate_required_fields(
    mapped_fields: List[str]
) -> Dict[str, any]:
    """
    Check that all required fields are present in the mapping.
    """
    required = ['date', 'sales_quantity']
    recommended = ['product_name', 'sku', 'sales_amount']

    present = set(mapped_fields)

    missing_required = [f for f in required if f not in present]
    missing_recommended = [f for f in recommended if f not in present]

    return {
        'is_valid': len(missing_required) == 0,
        'missing_required': missing_required,
        'missing_recommended': missing_recommended
    }