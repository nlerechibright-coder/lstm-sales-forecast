"""
Bulk invoice extraction service.
Parses CSV/Excel files containing multiple purchase records.
"""
import pandas as pd
from datetime import datetime
from typing import List, Dict, Any, Optional


class InvoiceExtractor:
    """
    Extracts purchase records from uploaded CSV/Excel files.
    
    Supports intelligent column alias matching for flexible imports.
    All date fields are returned as ISO-formatted strings for JSON serialization.
    """

    COLUMN_ALIASES = {
        'supplier': [
            'supplier', 'vendor', 'supplier_name', 'vendor_name', 
            'supplier name', 'vendor name', 'supplier company', 'vendor company'
        ],
        'product': [
            'product', 'item', 'product_name', 'item_name', 
            'product name', 'item name', 'description', 'product description',
            'item description', 'sku', 'product code', 'item code'
        ],
        'quantity': [
            'quantity', 'qty', 'units', 'quantity purchased', 'qty purchased',
            'quantity_ordered', 'ordered quantity', 'purchased quantity',
            'purchase quantity', 'amount', 'units purchased', 'qty ordered'
        ],
        'unit_cost': [
            'unit_cost', 'unit_price', 'cost', 'price', 'unit cost', 'unit price',
            'cost_price', 'cost price', 'purchase_price', 'purchase price',
            'buying_price', 'buying price', 'purchase_cost', 'purchase cost',
            'unit purchase price', 'cost per unit', 'price per unit'
        ],
        'date': [
            'date', 'purchase_date', 'order_date', 'purchase date', 'order date',
            'invoice_date', 'invoice date', 'date purchased', 'date ordered',
            'transaction date', 'receipt date'
        ],
        'invoice_number': [
            'invoice', 'invoice_number', 'invoice number', 'invoice_no', 
            'invoice no', 'bill_number', 'bill number', 'receipt_number',
            'receipt number', 'po_number', 'po number', 'order_number', 'order number'
        ],
    }

    REQUIRED_COLUMNS = ['supplier', 'product', 'quantity', 'unit_cost']

    @classmethod
    def parse_file(cls, file_obj) -> Dict[str, Any]:
        """
        Parse an uploaded CSV or Excel file.
        
        Returns:
            {
                'success': bool,
                'records': List[Dict],
                'errors': List[str],
                'total_rows': int,
                'valid_rows': int,
                'column_mapping': Dict[str, str],
            }
        """
        try:
            filename = file_obj.name.lower()
            
            if filename.endswith('.csv'):
                df = pd.read_csv(file_obj)
            elif filename.endswith(('.xlsx', '.xls')):
                df = pd.read_excel(file_obj)
            else:
                return {
                    'success': False,
                    'records': [],
                    'errors': ['Unsupported file format. Please upload CSV or Excel files.'],
                    'total_rows': 0,
                    'valid_rows': 0,
                    'column_mapping': {},
                }

            if df.empty:
                return {
                    'success': False,
                    'records': [],
                    'errors': ['The uploaded file is empty.'],
                    'total_rows': 0,
                    'valid_rows': 0,
                    'column_mapping': {},
                }

            # Map columns using intelligent alias matching
            column_mapping = cls._map_columns(df.columns)
            
            # Check for missing required columns
            missing = [col for col in cls.REQUIRED_COLUMNS if col not in column_mapping]
            if missing:
                found_columns = [str(col) for col in df.columns]
                error_msg = f'Missing required columns: {", ".join(missing)}.\n'
                error_msg += f'Found columns: {", ".join(found_columns)}\n'
                error_msg += f'Mapped columns: {column_mapping}\n'
                error_msg += f'Supported aliases for missing fields:\n'
                for field in missing:
                    aliases = cls.COLUMN_ALIASES.get(field, [])
                    error_msg += f'  - {field}: {", ".join(aliases[:5])}...\n'
                
                return {
                    'success': False,
                    'records': [],
                    'errors': [error_msg],
                    'total_rows': len(df),
                    'valid_rows': 0,
                    'column_mapping': column_mapping,
                }

            records = []
            errors = []

            for idx, row in df.iterrows():
                row_num = idx + 2  # Account for header row
                try:
                    record = cls._extract_row(row, column_mapping, row_num)
                    if record:
                        records.append(record)
                    else:
                        errors.append(f"Row {row_num}: Insufficient data")
                except Exception as e:
                    errors.append(f"Row {row_num}: {str(e)}")

            return {
                'success': len(records) > 0,
                'records': records,
                'errors': errors,
                'total_rows': len(df),
                'valid_rows': len(records),
                'column_mapping': column_mapping,
            }

        except Exception as e:
            return {
                'success': False,
                'records': [],
                'errors': [f'Failed to parse file: {str(e)}'],
                'total_rows': 0,
                'valid_rows': 0,
                'column_mapping': {},
            }

    @classmethod
    def _map_columns(cls, columns) -> Dict[str, str]:
        """
        Map file columns to standard field names using intelligent alias matching.
        
        This method:
        1. Normalizes column names (lowercase, strip whitespace)
        2. Matches against all defined aliases
        3. Returns mapping from standard field name to actual column name
        """
        mapping = {}
        
        # Create normalized column lookup: lowercase -> original column name
        columns_lower = {}
        for col in columns:
            normalized = str(col).strip().lower().replace('_', ' ').replace('-', ' ')
            columns_lower[normalized] = col
        
        # Also keep exact lowercase version for exact matching
        columns_exact = {str(col).strip().lower(): col for col in columns}

        for standard_name, aliases in cls.COLUMN_ALIASES.items():
            # Try exact match first
            for alias in aliases:
                alias_lower = alias.lower()
                if alias_lower in columns_exact:
                    mapping[standard_name] = columns_exact[alias_lower]
                    break
            
            # If no exact match, try normalized match (spaces/underscores interchangeable)
            if standard_name not in mapping:
                for alias in aliases:
                    alias_normalized = alias.lower().replace('_', ' ').replace('-', ' ')
                    if alias_normalized in columns_lower:
                        mapping[standard_name] = columns_lower[alias_normalized]
                        break

        return mapping

    @classmethod
    def _extract_row(cls, row, column_mapping: Dict[str, str], row_num: int) -> Optional[Dict]:
        """
        Extract a single row into a standardized record.
        
        All date fields are returned as ISO-formatted strings (YYYY-MM-DD)
        to ensure JSON serialization compatibility for session storage.
        """
        record = {}

        # Supplier
        supplier_val = row.get(column_mapping.get('supplier'))
        if pd.isna(supplier_val) or not str(supplier_val).strip():
            raise ValueError("Supplier name is empty")
        record['supplier_name'] = str(supplier_val).strip()

        # Product
        product_val = row.get(column_mapping.get('product'))
        if pd.isna(product_val) or not str(product_val).strip():
            raise ValueError("Product name is empty")
        record['product_name'] = str(product_val).strip()

        # Quantity
        qty_val = row.get(column_mapping.get('quantity'))
        if pd.isna(qty_val):
            raise ValueError("Quantity is empty")
        qty_str = str(qty_val).strip().replace(',', '').replace(' ', '')
        qty = int(float(qty_str))
        if qty <= 0:
            raise ValueError(f"Invalid quantity: {qty}")
        record['quantity'] = qty

        # Unit Cost
        cost_val = row.get(column_mapping.get('unit_cost'))
        if pd.isna(cost_val):
            raise ValueError("Unit cost is empty")
        cost_str = str(cost_val).strip().replace(',', '').replace('₦', '').replace('$', '').replace(' ', '')
        cost = float(cost_str)
        if cost <= 0:
            raise ValueError(f"Invalid unit cost: {cost}")
        record['unit_cost'] = round(cost, 2)
        record['total_cost'] = round(qty * cost, 2)

        # Date (optional) - ALWAYS return as ISO string for JSON serialization
        date_col = column_mapping.get('date')
        parsed_date = None
        
        if date_col:
            date_val = row.get(date_col)
            if not pd.isna(date_val):
                try:
                    if isinstance(date_val, datetime):
                        parsed_date = date_val.date()
                    elif isinstance(date_val, pd.Timestamp):
                        parsed_date = date_val.date()
                    else:
                        for fmt in ['%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y', '%d-%m-%Y', '%Y/%m/%d']:
                            try:
                                parsed_date = datetime.strptime(str(date_val).strip(), fmt).date()
                                break
                            except ValueError:
                                continue
                        if parsed_date is None:
                            parsed_date = pd.to_datetime(date_val).date()
                except Exception:
                    parsed_date = datetime.now().date()
        
        # Convert to ISO string for JSON serialization
        record['purchase_date'] = parsed_date.isoformat() if parsed_date else datetime.now().date().isoformat()

        # Invoice Number (optional)
        invoice_col = column_mapping.get('invoice_number')
        if invoice_col:
            invoice_val = row.get(invoice_col)
            if not pd.isna(invoice_val):
                record['invoice_number'] = str(invoice_val).strip()

        record['row_num'] = row_num
        return record