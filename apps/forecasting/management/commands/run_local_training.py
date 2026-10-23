from django.core.management.base import BaseCommand
from forecasting.services.training_service import TrainingService
from accounts.models import CustomUser, Company
from sales.models import Sales, DataImport
from django.utils import timezone

class Command(BaseCommand):
    help = 'Run LSTM training synchronously for local testing'

    def handle(self, *args, **kwargs):
        user = CustomUser.objects.first()
        if not user:
            self.stdout.write(self.style.ERROR("❌ No users found. Please register an account first."))
            return

        company = user.company
        if not company:
            company, _ = Company.objects.get_or_create(name="Local Demo Company")
            user.company = company
            user.save()
            self.stdout.write(f"✅ Created and assigned company: {company.name}")

        self.stdout.write(f"🔍 Checking database for Company ID: {company.id}")

        # Check Sales records
        sales_count = Sales.objects.filter(company=company).count()
        self.stdout.write(f"📊 Found {sales_count} Sales records for this company.")

        # Auto-fix: If this company has 0 sales, check if another company has them
        if sales_count == 0:
            total_sales = Sales.objects.count()
            self.stdout.write(self.style.WARNING(f"⚠️ Total sales in entire DB: {total_sales}"))
            
            if total_sales > 0:
                # Find the company that actually owns the uploaded data
                first_sale = Sales.objects.first()
                self.stdout.write(self.style.WARNING(f"💡 Sales data actually belongs to Company ID: {first_sale.company_id}"))
                
                # Reassign user to the correct company
                user.company_id = first_sale.company_id
                user.save()
                company = user.company
                self.stdout.write(self.style.SUCCESS(f"✅ Reassigned user to Company ID {first_sale.company_id}"))
            else:
                self.stdout.write(self.style.ERROR("❌ No sales data found anywhere. Please upload a CSV first."))
                return

        self.stdout.write(self.style.WARNING(f"🚀 Starting local synchronous training for Company ID: {company.id}..."))
        
        # Fast demo config
        config = {
            'lookback': 3,
            'epochs': 5,
            'lstm_units': 16,
        }

        try:
            service = TrainingService(company_id=company.id, config=config)
            result = service.train()
            
            self.stdout.write(self.style.SUCCESS("✅ Training completed successfully!"))
            self.stdout.write(f"MAE: {result.get('mae')}")
            self.stdout.write(f"RMSE: {result.get('rmse')}")
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Training failed: {str(e)}"))