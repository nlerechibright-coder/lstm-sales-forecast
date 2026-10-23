import os
import base64
from django.core.management.base import BaseCommand
from forecasting.models import ForecastModel

class Command(BaseCommand):
    help = 'Package locally trained model and deploy to the active database (e.g., live Neon DB)'

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.WARNING("🔍 Inspecting local database for the latest trained model..."))
        
        # 1. Get the latest trained model from the LOCAL database
        local_model = ForecastModel.objects.order_by('-created_at').first()
        
        if not local_model:
            self.stdout.write(self.style.ERROR("❌ No trained model found locally. Please run training first."))
            return

        model_path = local_model.model_path
        if not model_path or not os.path.exists(model_path):
            self.stdout.write(self.style.ERROR(f"❌ Model file not found at: {model_path}"))
            return

        self.stdout.write(f"📦 Found local model: {model_path}")
        
        # 2. Read and encode the model
        with open(model_path, 'rb') as f:
            model_bytes = f.read()
        model_blob = base64.b64encode(model_bytes).decode('utf-8')
        self.stdout.write(self.style.SUCCESS(f"✅ Model encoded to Base64 ({len(model_blob)} chars)"))

        company_id = local_model.company_id
        self.stdout.write(f"🎯 Target Company ID: {company_id}")

        # 3. Deactivate existing models for this company in the TARGET database
        ForecastModel.objects.filter(company_id=company_id, is_active=True, is_company_wide=True).update(is_active=False)

        # 4. Create the new model record in the TARGET database
        forecast_model = ForecastModel.objects.create(
            company_id=company_id,
            name="Deployed Local LSTM (Demo)",
            version=local_model.version,
            is_active=True,
            is_company_wide=True,
            architecture=local_model.architecture,
            feature_config=local_model.feature_config,
            model_path="database_blob", 
            model_blob=model_blob,
            scaler_config=local_model.scaler_config,
            training_samples=local_model.training_samples,
            validation_loss=local_model.validation_loss,
            training_loss=local_model.training_loss,
            epochs_trained=local_model.epochs_trained,
            trained_at=local_model.trained_at,
        )

        self.stdout.write(self.style.SUCCESS(f"🚀 Successfully deployed model to Company ID {company_id} in the active database!"))
        self.stdout.write(self.style.WARNING("⚠️  Restart your Render app to clear any cached states."))