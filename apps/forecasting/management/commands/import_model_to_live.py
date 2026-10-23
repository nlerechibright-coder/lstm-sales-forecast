import os
import json
from datetime import datetime
from django.core.management.base import BaseCommand
from forecasting.models import ForecastModel
from accounts.models import Company
from django.utils import timezone

class Command(BaseCommand):
    help = 'Import model from JSON file into the active (live) database'

    def handle(self, *args, **kwargs):
        if not os.path.exists('model_export.json'):
            self.stdout.write(self.style.ERROR("model_export.json not found. Run export first."))
            return

        with open('model_export.json', 'r') as f:
            data = json.load(f)

        # Find the first company in the LIVE database to ensure it exists
        target_company = Company.objects.first()
        if not target_company:
            self.stdout.write(self.style.ERROR("No companies found in the live database!"))
            return
        
        company_id = target_company.id
        self.stdout.write(f"🎯 Targeting live Company ID: {company_id}")

        # Deactivate existing models for this company
        ForecastModel.objects.filter(company=target_company, is_active=True, is_company_wide=True).update(is_active=False)

        trained_at = datetime.fromisoformat(data['trained_at']) if data['trained_at'] else timezone.now()
        if trained_at.tzinfo is None:
            trained_at = timezone.make_aware(trained_at)

        # Pass the company object directly to avoid lazy lookup errors in the save() method
        ForecastModel.objects.create(
            company=target_company,
            name="Deployed Local LSTM (Demo)",
            version=1,
            is_active=True,
            is_company_wide=True,
            architecture=data['architecture'],
            feature_config=data['feature_config'],
            model_path="database_blob",
            model_blob=data['model_blob'],
            scaler_config=data['scaler_config'],
            training_samples=data['training_samples'],
            validation_loss=data['validation_loss'],
            training_loss=data['training_loss'],
            epochs_trained=data['epochs_trained'],
            trained_at=trained_at,
        )
        self.stdout.write(self.style.SUCCESS(f"🚀 Successfully deployed model to Company {company_id} in live DB!"))