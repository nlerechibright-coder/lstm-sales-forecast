import io
from datetime import date

from django.test import TestCase, override_settings
from django.db import transaction

from accounts.models import Company
from django.contrib.auth import get_user_model

from procurement.services.invoice_extractor import InvoiceExtractor
from procurement.models import Supplier, PurchaseHistory
from inventory.models import Product


@override_settings(DATABASES={
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
})
class BulkUploadProcessingTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='TestCo')
        User = get_user_model()
        self.user = User.objects.create_user(username='tester', password='pass', company=self.company, role='owner')

        # Create one existing product to test update path
        Product.objects.create(
            company=self.company,
            name='Widget A',
            base_price=100.0,
            cost_price=200.0,
            current_stock=5,
        )

    def test_bulk_confirm_creates_purchase_history(self):
        csv = 'supplier,product,quantity,unit_cost,date\nAcme Supplies,Widget A,10,250.50,2026-07-01\nAcme Supplies,Widget B,5,100,2026-07-02\n'
        f = io.BytesIO(csv.encode())
        f.name = 'test.csv'

        result = InvoiceExtractor.parse_file(f)
        self.assertTrue(result['success'])
        records = result['records']

        auto_suppliers = True
        auto_products = True

        with transaction.atomic():
            for record in records:
                # Resolve or create supplier (same logic as the view)
                supplier = Supplier.objects.filter(
                    company=self.company,
                    name__iexact=record['supplier_name']
                ).first()
                if not supplier:
                    if auto_suppliers:
                        supplier = Supplier.objects.create(
                            company=self.company,
                            name=record['supplier_name'],
                            status='active',
                            created_by=self.user,
                        )
                    else:
                        continue

                # Product resolution
                product = Product.objects.filter(
                    company=self.company,
                    name__iexact=record['product_name']
                ).first()

                if not product:
                    rec_name_lower = record['product_name'].lower().strip()
                    for p in Product.objects.filter(company=self.company):
                        p_name_lower = p.name.lower().strip()
                        if len(p_name_lower) >= 4 and len(rec_name_lower) >= 4:
                            if p_name_lower in rec_name_lower or rec_name_lower in p_name_lower:
                                product = p
                                break

                if not product:
                    if auto_products:
                        product = Product.objects.create(
                            company=self.company,
                            name=record['product_name'],
                            base_price=record['unit_cost'] * 1.3,
                            cost_price=record['unit_cost'],
                            current_stock=record['quantity'],
                        )
                    else:
                        continue
                else:
                    product.current_stock += record['quantity']
                    product.cost_price = record['unit_cost']
                    product.save()

                PurchaseHistory.objects.create(
                    company=self.company,
                    supplier=supplier,
                    product=product,
                    quantity=record['quantity'],
                    unit_cost=record['unit_cost'],
                    total_cost=record['total_cost'],
                    purchase_date=record.get('purchase_date'),
                    received_date=date.today(),
                    created_by=self.user,
                )

        self.assertEqual(PurchaseHistory.objects.filter(company=self.company).count(), 2)
