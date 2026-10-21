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
    
    Expected columns (flexible matching):
    - Supplier / Vendor / Supplier Name
    - Product / Item / Product Name
    - Quantity / Qty / Units
    - Unit Cost / Unit Price / Cost / Price
    - Date / Purchase Date / Order Date
    """

    COLUMN_ALIASES = {
        'supplier': ['supplier', 'vendor', 'supplier_name', 'vendor_name', 'supplier name', 'vendor name'],
        'product': ['product', 'item', 'product_name', 'item_name', 'product name', 'item name', 'description'],
        'quantity': ['quantity', 'qty', 'units', 'quantity purchased', 'qty purchased', 'quantity_ordered'],
        'unit_cost': ['unit_cost', 'unit_price', 'cost', 'price', 'unit cost', 'unit price', 'cost_price', 'cost price'],
        'date': ['date', 'purchase_date', 'order_date', 'purchase date', 'order date', 'invoice_date'],
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
                }

            if df.empty:
                return {
                    'success': False,
                    'records': [],
                    'errors': ['The uploaded file is empty.'],
                    'total_rows': 0,
                    'valid_rows': 0,
                }

            # Map columns
            column_mapping = cls._map_columns(df.columns)
            
            missing = [col for col in cls.REQUIRED_COLUMNS if col not in column_mapping]
            if missing:
                return {
                    'success': False,
                    'records': [],
                    'errors': [f'Missing required columns: {", ".join(missing)}. Found columns: {", ".join(df.columns)}'],
                    'total_rows': len(df),
                    'valid_rows': 0,
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
            }

        except Exception as e:
            return {
                'success': False,
                'records': [],
                'errors': [f'Failed to parse file: {str(e)}'],
                'total_rows': 0,
                'valid_rows': 0,
            }

    @classmethod
    def _map_columns(cls, columns) -> Dict[str, str]:
        """Map file columns to standard field names."""
        mapping = {}
        columns_lower = {str(col).strip().lower(): col for col in columns}

        for standard_name, aliases in cls.COLUMN_ALIASES.items():
            for alias in aliases:
                if alias in columns_lower:
                    mapping[standard_name] = columns_lower[alias]
                    break

        return mapping

    @classmethod
    def _extract_row(cls, row, column_mapping: Dict[str, str], row_num: int) -> Optional[Dict]:
        """Extract a single row into a standardized record."""
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
        qty = int(float(str(qty_val).strip().replace(',', '')))
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

        # Date (optional)
        date_col = column_mapping.get('date')
        if date_col:
            date_val = row.get(date_col)
            if not pd.isna(date_val):
                try:
                    if isinstance(date_val, datetime):
                        record['purchase_date'] = date_val.date()
                    elif isinstance(date_val, pd.Timestamp):
                        record['purchase_date'] = date_val.date()
                    else:
                        for fmt in ['%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y', '%d-%m-%Y']:
                            try:
                                record['purchase_date'] = datetime.strptime(str(date_val).strip(), fmt).date()
                                break
                            except ValueError:
                                continue
                        if 'purchase_date' not in record:
                            record['purchase_date'] = pd.to_datetime(date_val).date()
                except Exception:
                    record['purchase_date'] = datetime.now().date()
            else:
                record['purchase_date'] = datetime.now().date()
        else:
            record['purchase_date'] = datetime.now().date()

        record['row_num'] = row_num
        return record