import os
import json
import base64
from django.core.management.base import BaseCommand
from forecasting.models import ForecastModel

class Command(BaseCommand):
    help = 'Export locally trained model to a JSON file for deployment'

    def handle(self, *args, **kwargs):
        model = ForecastModel.objects.order_by('-created_at').first()
        if not model:
            self.stdout.write(self.style.ERROR("No model found locally."))
            return
        
        model_path = model.model_path
        if not os.path.exists(model_path):
            self.stdout.write(self.style.ERROR(f"Model file not found: {model_path}"))
            return

        with open(model_path, 'rb') as f:
            blob = base64.b64encode(f.read()).decode('utf-8')

        data = {
            'company_id': model.company_id,
            'architecture': model.architecture,
            'feature_config': model.feature_config,
            'scaler_config': model.scaler_config,
            'model_blob': blob,
            'training_samples': model.training_samples,
            'validation_loss': model.validation_loss,
            'training_loss': model.training_loss,
            'epochs_trained': model.epochs_trained,
            'trained_at': model.trained_at.isoformat() if model.trained_at else None,
        }

        with open('model_export.json', 'w') as f:
            json.dump(data, f)
        
        self.stdout.write(self.style.SUCCESS(f"✅ Exported model for Company {model.company_id} to model_export.json"))