from typing import Dict, Any, Optional, Tuple
from django.conf import settings


class TrainingConfigValidator:
    """Validates hyperparameters before training begins."""
    
    ALLOWED_LOOKBACK = range(14, 366)       # 14 days to 1 year
    ALLOWED_EPOCHS = range(10, 1001)        # 10 to 1000
    ALLOWED_LSTM_UNITS = [16, 32, 64, 128, 256]
    
    @classmethod
    def validate(cls, config: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Returns (is_valid, error_message).
        """
        lookback = config.get('lookback', 30)
        epochs = config.get('epochs', 100)
        lstm_units = config.get('lstm_units', 64)
        
        if lookback not in cls.ALLOWED_LOOKBACK:
            return False, f"Lookback must be between 14 and 365 days. Got {lookback}."
            
        if epochs not in cls.ALLOWED_EPOCHS:
            return False, f"Epochs must be between 10 and 1000. Got {epochs}."
            
        if lstm_units not in cls.ALLOWED_LSTM_UNITS:
            return False, f"LSTM units must be one of {cls.ALLOWED_LSTM_UNITS}. Got {lstm_units}."
            
        return True, None


class ForecastConfigValidator:
    """Validates forecast generation parameters."""

    SUPPORTED_DAYS_AHEAD = tuple(settings.FORECAST_SUPPORTED_HORIZONS)
    DEFAULT_DAYS_AHEAD = settings.FORECAST_DEFAULT_HORIZON

    @classmethod
    def validate(cls, days_ahead: int) -> Tuple[bool, Optional[str]]:
        if not 1 <= days_ahead <= settings.FORECAST_MAX_HORIZON:
            return False, (
                f"Days ahead must be between 1 and "
                f"{settings.FORECAST_MAX_HORIZON}. Got {days_ahead}."
            )
        return True, None
