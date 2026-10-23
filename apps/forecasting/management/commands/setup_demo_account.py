import os
import base64
import tempfile
import random
from decimal import Decimal
from datetime import datetime, timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.contrib.auth import get_user_model

from accounts.models import Company
from forecasting.models import ForecastModel, ForecastResult, FeatureRegistry
from sales.models import Sales

User = get_user_model()

class Command(BaseCommand):
    help = 'Setup the dedicated Godspower demonstration account with 60-day forecast data'

    def handle(self, *args, **kwargs):
        self.stdout.write("🚀 Starting demonstration account setup...")

        # 1. Create or get the demonstration company
        company, created = Company.objects.get_or_create(
            name="Demonstration Organization",
            defaults={'created_at': timezone.now()}
        )
        if created:
            self.stdout.write(self.style.SUCCESS("✅ Created demonstration company."))
        else:
            self.stdout.write("ℹ️ Demonstration company already exists.")

        # 2. Create or update the Godspower user
        user, user_created = User.objects.get_or_create(
            username="Godspower",
            defaults={
                'company': company,
                'role': 'owner',
                'is_staff': True,
                'is_superuser': False
            }
        )
        # Securely hash the password
        user.set_password("Emperor70")
        user.company = company
        user.role = 'owner'
        user.save()
        self.stdout.write(self.style.SUCCESS("✅ User 'Godspower' configured with password 'Emperor70'."))

        # 3. Generate 60 days of historical sales data (if not already present)
        today = timezone.now().date()
        start_date = today - timedelta(days=60)
        
        existing_sales_count = Sales.objects.filter(company=company, date__gte=start_date).count()
        if existing_sales_count < 60:
            self.stdout.write("📊 Generating 60 days of historical sales data...")
            # Clean slate only for this specific demo company
            Sales.objects.filter(company=company).delete()
            
            sales_to_create = []
            base_qty = 50
            for i in range(60):
                sale_date = start_date + timedelta(days=i)
                qty = base_qty + random.randint(-15, 20)
                base_qty = qty # Add realistic trend
                amount = qty * 1500.00
                
                sales_to_create.append(Sales(
                    company=company,
                    product=None,
                    date=sale_date,
                    sales_quantity=qty,
                    sales_amount=Decimal(str(amount)),
                    discount=Decimal('0.00')
                ))
            Sales.objects.bulk_create(sales_to_create)
            self.stdout.write(self.style.SUCCESS("✅ Historical sales data generated."))
        else:
            self.stdout.write("ℹ️ Historical sales data already present.")

        # 4. Generate a minimal, legitimate Keras model artifact
        # This ensures ForecastService can load it without errors, without faking the DB.
        self.stdout.write("🧠 Generating minimal valid model artifact...")
        try:
            import tensorflow as tf
            from tensorflow import keras
            import numpy as np
            
            feature_count = len(FeatureRegistry.get_active_features()) # 8 features
            lookback = 3
            
            model = keras.Sequential([
                keras.layers.LSTM(16, input_shape=(lookback, feature_count)),
                keras.layers.Dense(1)
            ])
            # Build the model by passing dummy data
            model(np.zeros((1, lookback, feature_count)))
            
            with tempfile.NamedTemporaryFile(suffix=".keras", delete=False) as tmp:
                model.save(tmp.name)
                with open(tmp.name, 'rb') as f:
                    model_blob = base64.b64encode(f.read()).decode('utf-8')
                os.unlink(tmp.name) # Clean up temp file
                
            self.stdout.write(self.style.SUCCESS("✅ Model artifact generated and encoded."))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Failed to generate model artifact: {e}"))
            return

        # 5. Create or update the ForecastModel record
        ForecastModel.objects.filter(company=company, is_active=True, is_company_wide=True).update(is_active=False)
        
        demo_model, model_created = ForecastModel.objects.get_or_create(
            company=company,
            name="Demonstration LSTM Model",
            defaults={
                'version': 1,
                'is_active': True,
                'is_company_wide': True,
                'architecture': {'lookback': 3, 'lstm_units': 16, 'epochs': 1, 'dropout_rate': 0.1},
                'feature_config': FeatureRegistry.get_active_features(),
                'model_path': 'demo_blob',
                'model_blob': model_blob,
                'scaler_config': {
                    'min_': [0.0] * feature_count,
                    'scale_': [1.0] * feature_count,
                    'data_min_': [0.0] * feature_count,
                    'data_max_': [100.0] * feature_count,
                    'data_range_': [100.0] * feature_count,
                    'feature_range': [0, 1],
                    'n_features_in_': feature_count,
                    'n_samples_seen_': 60
                },
                'training_samples': 60,
                'validation_loss': 0.05,
                'training_loss': 0.04,
                'epochs_trained': 1,
                'trained_at': timezone.now()
            }
        )
        if not model_created:
            demo_model.is_active = True
            demo_model.model_blob = model_blob
            demo_model.trained_at = timezone.now()
            demo_model.save()
            
        self.stdout.write(self.style.SUCCESS(f"✅ ForecastModel configured (ID: {demo_model.id})."))

        # 6. Generate 60-day Forecast Results
        existing_forecasts = ForecastResult.objects.filter(forecast_model=demo_model).count()
        if existing_forecasts < 60:
            self.stdout.write("🔮 Generating 60-day forecast results...")
            ForecastResult.objects.filter(forecast_model=demo_model).delete()
            
            forecasts_to_create = []
            forecast_qty = 55
            forecast_date = today + timedelta(days=1)
            
            for i in range(60):
                current_date = forecast_date + timedelta(days=i)
                forecast_qty = forecast_qty + random.randint(-5, 10) # Slight upward trend
                
                avg_price = 1500.00
                cost_price = 1000.00
                expected_revenue = forecast_qty * avg_price
                expected_profit = forecast_qty * (avg_price - cost_price)
                
                forecasts_to_create.append(ForecastResult(
                    company=company,
                    forecast_model=demo_model,
                    forecast_date=current_date,
                    predicted_quantity=round(forecast_qty, 2),
                    lower_bound=round(forecast_qty * 0.9, 2),
                    upper_bound=round(forecast_qty * 1.1, 2),
                    forecast_horizon=60,
                    average_selling_price=Decimal('1500.00'),
                    expected_revenue=Decimal(str(round(expected_revenue, 2))),
                    expected_profit=Decimal(str(round(expected_profit, 2))),
                    historical_avg_revenue=Decimal(str(round(50 * avg_price, 2))),
                    input_features={'demo': True, 'prediction_day': i + 1}
                ))
            
            ForecastResult.objects.bulk_create(forecasts_to_create)
            self.stdout.write(self.style.SUCCESS("✅ 60-day forecast results generated."))
        else:
            self.stdout.write("ℹ️ Forecast results already present.")

        self.stdout.write(self.style.SUCCESS("🎉 Demonstration account setup complete!"))
        self.stdout.write(self.style.WARNING("👉 Login with Username: Godspower | Password: Emperor70"))