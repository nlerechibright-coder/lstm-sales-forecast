import os
import io
import sys
import json
import numpy as np
import pandas as pd
from datetime import datetime
from typing import Dict, Optional, Tuple
from django.conf import settings
from django.db import transaction
from sklearn.preprocessing import MinMaxScaler
from sklearn.metrics import mean_absolute_error, mean_squared_error

from sales.models import Sales
from forecasting.models import ForecastModel, ForecastRun, FeatureRegistry
from forecasting.services.preprocessing_service import PreprocessingService
from forecasting.services.progress_tracker import update_run_progress, clear_run_progress


class LogCapture:
    """Captures stdout/stderr during training."""
    def __init__(self):
        self.stdout = io.StringIO()
        self.stderr = io.StringIO()
        self.old_stdout = None
        self.old_stderr = None
    
    def __enter__(self):
        self.old_stdout = sys.stdout
        self.old_stderr = sys.stderr
        sys.stdout = self.stdout
        sys.stderr = self.stderr
        return self
    
    def __exit__(self, *args):
        sys.stdout = self.old_stdout
        sys.stderr = self.old_stderr
    
    def get_logs(self):
        return self.stdout.getvalue() + self.stderr.getvalue()


class TrainingService:
    """
    End-to-end LSTM training pipeline scoped per company.
    """

    # =====================================================================
    # TEMPORARY SETTINGS FOR DEMO / DEFENSE (7-Day CSV)
    # Revert these back to production values after the demo!
    # =====================================================================
    DEFAULT_CONFIG = {
        'lookback': 3,           # Reduced from 30 (Must be smaller than 7-day CSV)
        'lstm_units': 16,        # Reduced for fast CPU training
        'dropout_rate': 0.1,
        'dense_units': 8,        # Reduced for fast CPU training
        'learning_rate': 0.01,   # Increased to converge faster
        'batch_size': 8,         # Reduced to prevent RAM crashes
        'epochs': 5,             # Reduced from 100 (Will finish in ~10-20 mins)
        'validation_split': 0.2,
        'early_stop_patience': 2,
    }

    def __init__(self, company_id: int, config: Optional[Dict] = None):
        self.company_id = company_id
        self.config = {**self.DEFAULT_CONFIG, **(config or {})}
        self.preprocessor = PreprocessingService(company_id=company_id)
        self.scaler = None
        self.model = None
        self.feature_names = None
        self.training_logs = []

    def _log(self, message: str):
        """Add a log message."""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_entry = f"[{timestamp}] {message}"
        self.training_logs.append(log_entry)

    @staticmethod
    def get_retraining_status(
        company_id: int,
        min_new_days: Optional[int] = None,
        min_total_days: Optional[int] = None,
    ) -> Dict:
        """Return whether a company should trigger a retraining cycle."""
        min_new_days = min_new_days or settings.FORECAST_AUTO_RETRAIN_MIN_NEW_DAYS
        min_total_days = min_total_days or settings.FORECAST_AUTO_RETRAIN_MIN_TOTAL_DAYS
        total_days = Sales.objects.filter(company_id=company_id).values('date').distinct().count()

        if total_days < min_total_days:
            return {
                'should_retrain': False,
                'reason': 'insufficient_data',
                'total_sales_days': total_days,
                'minimum_required_days': min_total_days,
            }

        active_model = ForecastModel.objects.filter(
            company_id=company_id,
            is_active=True,
            is_company_wide=True,
        ).first()

        if not active_model:
            return {
                'should_retrain': True,
                'reason': 'no_active_model',
                'total_sales_days': total_days,
                'minimum_required_days': min_total_days,
            }

        if ForecastRun.objects.filter(
            company_id=company_id,
            status__in=['PENDING', 'RUNNING']
        ).exists():
            return {
                'should_retrain': False,
                'reason': 'training_in_progress',
                'total_sales_days': total_days,
                'minimum_required_days': min_total_days,
            }

        last_trained_date = active_model.trained_at.date() if active_model.trained_at else None
        if last_trained_date is None:
            return {
                'should_retrain': True,
                'reason': 'no_training_timestamp',
                'total_sales_days': total_days,
                'minimum_required_days': min_total_days,
            }

        new_data_days = Sales.objects.filter(
            company_id=company_id,
            date__gt=last_trained_date,
        ).values('date').distinct().count()

        if new_data_days < min_new_days:
            return {
                'should_retrain': False,
                'reason': 'insufficient_new_data',
                'total_sales_days': total_days,
                'new_data_days': new_data_days,
                'minimum_required_days': min_total_days,
                'minimum_new_days': min_new_days,
                'last_trained_date': last_trained_date,
            }

        return {
            'should_retrain': True,
            'reason': 'new_data_available',
            'total_sales_days': total_days,
            'new_data_days': new_data_days,
            'minimum_required_days': min_total_days,
            'minimum_new_days': min_new_days,
            'last_trained_date': last_trained_date,
        }

    def train(self, run_id: Optional[int] = None) -> Dict:
        # =====================================================================
        # LAZY LOAD TENSORFLOW HERE
        # This prevents TensorFlow from loading into memory on every web request,
        # which was causing Out-Of-Memory (SIGKILL) crashes on Render's free tier.
        # =====================================================================
        import tensorflow as tf
        from tensorflow import keras
        from tensorflow.keras.models import Sequential
        from tensorflow.keras.layers import LSTM, Dense, Dropout
        from tensorflow.keras.callbacks import EarlyStopping, ModelCheckpoint
        from tensorflow.keras.optimizers import Adam

        # Define ProgressCallback locally so it has access to the lazily-loaded keras
        class ProgressCallback(keras.callbacks.Callback):
            def __init__(self, run_id, total_epochs):
                super().__init__()
                self.run_id = run_id
                self.total_epochs = total_epochs

            def on_epoch_begin(self, epoch, logs=None):
                if self.run_id:
                    update_run_progress(self.run_id, epoch + 1, self.total_epochs, f"Training Epoch {epoch + 1}/{self.total_epochs}")

            def on_epoch_end(self, epoch, logs=None):
                if self.run_id and logs:
                    val_loss = logs.get('val_loss', 0)
                    update_run_progress(self.run_id, epoch + 1, self.total_epochs, f"Epoch {epoch + 1}/{self.total_epochs} | Val Loss: {val_loss:.4f}")

        # =====================================================================
        # END LAZY LOAD
        # =====================================================================

        run = self._get_or_create_run(run_id)
        
        self._log(f"Starting training for company {self.company_id}")
        self._log(f"Configuration: {json.dumps(self.config)}")
        
        run.status = 'RUNNING'
        run.started_at = datetime.now()
        run.save()

        try:
            self._log("Building training dataframe...")
            df = self.preprocessor.build_training_dataframe()

            # TEMPORARY FOR DEMO: Changed minimum from lookback * 2 (60) to 7 days
            if df.empty or len(df) < 7:
                raise ValueError(
                    f"Insufficient data: {len(df)} records. "
                    f"Need at least 7 days for demo training."
                )

            self._log(f"Dataset prepared: {len(df)} records from {df.index.min()} to {df.index.max()}")

            run.total_records = len(df)
            run.data_start_date = df.index.min()
            run.data_end_date = df.index.max()
            run.save()

            self._log("Scaling features...")
            scaled_data, feature_names = self._scale_data(df)
            self.feature_names = feature_names
            target_idx = feature_names.index(FeatureRegistry.get_target_feature())

            self._log("Creating sequences...")
            X, y = PreprocessingService.create_sequences(
                scaled_data, target_idx, self.config['lookback']
            )

            split_idx = int(len(X) * (1 - self.config['validation_split']))
            X_train, X_val = X[:split_idx], X[split_idx:]
            y_train, y_val = y[:split_idx], y[split_idx:]

            self._log(f"Train/Val split: {len(X_train)} training samples, {len(X_val)} validation samples")

            self._log("Building LSTM model...")
            self.model = self._build_model(input_shape=(X.shape[1], X.shape[2]), keras=keras, Sequential=Sequential, LSTM=LSTM, Dense=Dense, Dropout=Dropout, Adam=Adam)

            model_dir = os.path.join(settings.MEDIA_ROOT, 'forecast_models', str(self.company_id))
            os.makedirs(model_dir, exist_ok=True)

            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            model_filename = f"lstm_{timestamp}.keras"
            model_path = os.path.join(model_dir, model_filename)

            self._log(f"Model will be saved to: {model_path}")

            callbacks = [
                EarlyStopping(
                    monitor='val_loss',
                    patience=self.config['early_stop_patience'],
                    restore_best_weights=True,
                    verbose=1
                ),
                ModelCheckpoint(
                    filepath=model_path,
                    monitor='val_loss',
                    save_best_only=True,
                    verbose=1
                ),
                ProgressCallback(run.id, self.config['epochs'])
            ]

            self._log(f"Starting training for {self.config['epochs']} epochs...")
            
            with LogCapture() as log_capture:
                history = self.model.fit(
                    X_train, y_train,
                    validation_data=(X_val, y_val),
                    epochs=self.config['epochs'],
                    batch_size=self.config['batch_size'],
                    callbacks=callbacks,
                    verbose=1
                )
                
                keras_logs = log_capture.get_logs()
                self.training_logs.append(keras_logs)

            self._log("Training complete. Evaluating model...")

            val_preds = self.model.predict(X_val, verbose=0).flatten()

            val_preds_inv = self._inverse_transform_target(val_preds)
            y_val_inv = self._inverse_transform_target(y_val)

            mae = mean_absolute_error(y_val_inv, val_preds_inv)
            rmse = np.sqrt(mean_squared_error(y_val_inv, val_preds_inv))
            mape = np.mean(np.abs((y_val_inv - val_preds_inv) / (y_val_inv + 1e-8))) * 100

            self._log(f"Metrics - MAE: {mae:.4f}, RMSE: {rmse:.4f}, MAPE: {mape:.2f}%")

            with transaction.atomic():
                version = ForecastModel.objects.filter(
                    company_id=self.company_id,
                    is_company_wide=True
                ).count() + 1

                forecast_model = ForecastModel.objects.create(
                    company_id=self.company_id,
                    name=f"Company-Wide LSTM v{version}",
                    version=version,
                    is_active=True,
                    architecture=self.config,
                    feature_config=FeatureRegistry.get_active_features(),
                    model_path=model_path,
                    scaler_config=self._serialize_scaler(),
                    training_samples=len(X_train),
                    validation_loss=float(min(history.history['val_loss'])),
                    training_loss=float(min(history.history['loss'])),
                    epochs_trained=len(history.history['loss']),
                    is_company_wide=True,
                    product=None,
                    trained_at=datetime.now()
                )

                run.status = 'COMPLETED'
                run.forecast_model = forecast_model
                run.mae = float(mae)
                run.rmse = float(rmse)
                run.mape = float(mape)
                run.completed_at = datetime.now()
                run.training_log = '\n'.join(self.training_logs)
                run.save()

            if run.id:
                clear_run_progress(run.id)

            self._log(f"Model v{version} created and activated successfully")

            return {
                'success': True,
                'model_id': forecast_model.id,
                'version': version,
                'mae': mae,
                'rmse': rmse,
                'mape': mape,
                'epochs_trained': len(history.history['loss']),
                'training_samples': len(X_train),
                'validation_samples': len(X_val),
                'model_path': model_path,
            }

        except Exception as e:
            self._log(f"ERROR: {str(e)}")
            if run.id:
                clear_run_progress(run.id)
            run.status = 'FAILED'
            run.error_message = str(e)
            run.completed_at = datetime.now()
            run.training_log = '\n'.join(self.training_logs)
            run.save()
            raise

    def _build_model(self, input_shape: Tuple[int, int], keras, Sequential, LSTM, Dense, Dropout, Adam) -> 'keras.Model':
        model = Sequential([
            LSTM(
                self.config['lstm_units'],
                return_sequences=True,
                input_shape=input_shape
            ),
            Dropout(self.config['dropout_rate']),
            LSTM(self.config['lstm_units'] // 2),
            Dropout(self.config['dropout_rate']),
            Dense(self.config['dense_units'], activation='relu'),
            Dense(1)
        ])

        optimizer = Adam(learning_rate=self.config['learning_rate'])
        model.compile(optimizer=optimizer, loss='mse', metrics=['mae'])

        return model

    def _scale_data(self, df: pd.DataFrame) -> Tuple[np.ndarray, list]:
        self.scaler = MinMaxScaler(feature_range=(0, 1))
        scaled = self.scaler.fit_transform(df.values)
        return scaled, list(df.columns)

    def _serialize_scaler(self) -> Dict:
        return {
            'min_': self.scaler.min_.tolist(),
            'scale_': self.scaler.scale_.tolist(),
            'data_min_': self.scaler.data_min_.tolist(),
            'data_max_': self.scaler.data_max_.tolist(),
            'data_range_': self.scaler.data_range_.tolist(),
            'feature_range': self.scaler.feature_range,
            'n_features_in_': self.scaler.n_features_in_,
            'n_samples_seen_': int(self.scaler.n_samples_seen_),
        }

    def _inverse_transform_target(self, scaled_values: np.ndarray) -> np.ndarray:
        target_idx = self.feature_names.index(FeatureRegistry.get_target_feature())
        dummy = np.zeros((len(scaled_values), self.scaler.n_features_in_))
        dummy[:, target_idx] = scaled_values
        inv = self.scaler.inverse_transform(dummy)
        return inv[:, target_idx]

    def _get_or_create_run(self, run_id: Optional[int]) -> ForecastRun:
        if run_id:
            return ForecastRun.objects.get(id=run_id, company_id=self.company_id)
        return ForecastRun.objects.create(
            company_id=self.company_id,
            run_type='TRAIN',
            status='PENDING'
        )