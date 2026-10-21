from django.test import TestCase

from forecasting.services.training_service import TrainingService
from forecasting.services.validation_service import ForecastConfigValidator


class ForecastingHorizonAndRetrainingTests(TestCase):
    def test_60_day_forecast_is_allowed(self):
        is_valid, error = ForecastConfigValidator.validate(60)
        self.assertTrue(is_valid, error)

    def test_retraining_is_blocked_when_data_is_insufficient(self):
        status = TrainingService.get_retraining_status(company_id=9999)
        self.assertFalse(status['should_retrain'])
        self.assertEqual(status['reason'], 'insufficient_data')
