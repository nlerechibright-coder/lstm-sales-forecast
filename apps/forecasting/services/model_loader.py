"""
Model Loader Service — Stub for ML Integration

This module provides a clean interface for loading trained LSTM models
and their associated scalers. It is designed to be extended in future phases
for model versioning, caching, and warm-loading.

Current implementation: Direct filesystem loading.
Future extensions:
  - Model caching in memory (Redis/in-process)
  - Model versioning with rollback support
  - Lazy loading for memory efficiency
  - Model health checks before prediction
"""
import os
import logging
from typing import Optional, Dict
from tensorflow import keras
from sklearn.preprocessing import MinMaxScaler
import numpy as np

from forecasting.models import ForecastModel

logger = logging.getLogger(__name__)


class ModelLoader:
    """
    Loads and manages trained forecasting models.
    Company-scoped — each company loads only its own models.
    """

    def __init__(self, company_id: int):
        self.company_id = company_id
        self._model = None
        self._scaler = None
        self._model_record = None

    def load_active_model(self) -> Optional[ForecastModel]:
        """
        Load the currently active model for this company.
        Returns the ForecastModel record if successful, None otherwise.
        """
        try:
            model_record = ForecastModel.objects.filter(
                company_id=self.company_id,
                is_active=True,
                is_company_wide=True
            ).first()

            if not model_record:
                logger.warning(f"No active model found for company {self.company_id}")
                return None

            if not model_record.model_path:
                logger.warning(f"Model record exists but no model_path for company {self.company_id}")
                return None

            if not os.path.exists(model_record.model_path):
                logger.error(f"Model file not found at {model_record.model_path}")
                return None

            self._model = keras.models.load_model(model_record.model_path)
            self._scaler = self._deserialize_scaler(model_record.scaler_config)
            self._model_record = model_record

            logger.info(
                f"Loaded model v{model_record.version} for company {self.company_id}"
            )

            return model_record

        except Exception as e:
            logger.error(f"Failed to load model for company {self.company_id}: {e}")
            return None

    def load_specific_model(self, model_id: int) -> Optional[ForecastModel]:
        """
        Load a specific model by ID.
        """
        try:
            model_record = ForecastModel.objects.get(
                id=model_id,
                company_id=self.company_id
            )

            if not model_record.model_path or not os.path.exists(model_record.model_path):
                return None

            self._model = keras.models.load_model(model_record.model_path)
            self._scaler = self._deserialize_scaler(model_record.scaler_config)
            self._model_record = model_record

            return model_record

        except ForecastModel.DoesNotExist:
            return None
        except Exception as e:
            logger.error(f"Failed to load model {model_id}: {e}")
            return None

    @property
    def model(self):
        return self._model

    @property
    def scaler(self):
        return self._scaler

    @property
    def model_record(self):
        return self._model_record

    @property
    def feature_names(self):
        if self._model_record and self._model_record.feature_config:
            return [f['name'] for f in self._model_record.feature_config]
        return []

    @property
    def architecture(self):
        if self._model_record:
            return self._model_record.architecture
        return {}

    def is_loaded(self) -> bool:
        """Check if a model is currently loaded."""
        return self._model is not None and self._scaler is not None

    def _deserialize_scaler(self, scaler_config: Dict) -> MinMaxScaler:
        """Reconstruct MinMaxScaler from stored JSON config."""
        scaler = MinMaxScaler(feature_range=tuple(scaler_config['feature_range']))
        scaler.min_ = np.array(scaler_config['min_'])
        scaler.scale_ = np.array(scaler_config['scale_'])
        scaler.data_min_ = np.array(scaler_config['data_min_'])
        scaler.data_max_ = np.array(scaler_config['data_max_'])
        scaler.data_range_ = np.array(scaler_config['data_range_'])
        scaler.n_features_in_ = scaler_config['n_features_in_']
        scaler.n_samples_seen_ = scaler_config['n_samples_seen_']
        return scaler

    def predict(self, X):
        """
        Run prediction on loaded model.
        Placeholder for future extensions (batching, confidence intervals, etc.)
        """
        if not self.is_loaded():
            raise RuntimeError("No model loaded. Call load_active_model() first.")
        return self._model.predict(X, verbose=0)

    def unload(self):
        """Release model from memory."""
        self._model = None
        self._scaler = None
        self._model_record = None
        logger.info(f"Model unloaded for company {self.company_id}")