from typing import Dict, Tuple

class TrainingConfigValidator:
    """Validates training configuration parameters."""
    
    # DEMO MODE: Lowered minimums for 7-day fast testing
    MIN_LOOKBACK = 2
    MAX_LOOKBACK = 90
    MIN_EPOCHS = 1
    MAX_EPOCHS = 200
    MIN_LSTM_UNITS = 8
    MAX_LSTM_UNITS = 256

    @staticmethod
    def validate(config: Dict) -> Tuple[bool, str]:
        lookback = config.get('lookback', 3)
        epochs = config.get('epochs', 5)
        lstm_units = config.get('lstm_units', 16)

        if not (TrainingConfigValidator.MIN_LOOKBACK <= lookback <= TrainingConfigValidator.MAX_LOOKBACK):
            return False, f"Lookback must be between {TrainingConfigValidator.MIN_LOOKBACK} and {TrainingConfigValidator.MAX_LOOKBACK} days."
        
        if not (TrainingConfigValidator.MIN_EPOCHS <= epochs <= TrainingConfigValidator.MAX_EPOCHS):
            return False, f"Epochs must be between {TrainingConfigValidator.MIN_EPOCHS} and {TrainingConfigValidator.MAX_EPOCHS}."
        
        if not (TrainingConfigValidator.MIN_LSTM_UNITS <= lstm_units <= TrainingConfigValidator.MAX_LSTM_UNITS):
            return False, f"LSTM Units must be between {TrainingConfigValidator.MIN_LSTM_UNITS} and {TrainingConfigValidator.MAX_LSTM_UNITS}."

        return True, ""


class ForecastConfigValidator:
    """Validates forecast generation parameters."""
    
    # DEMO MODE: Allow 7 days
    MIN_DAYS_AHEAD = 7
    MAX_DAYS_AHEAD = 365
    DEFAULT_DAYS_AHEAD = 7
    SUPPORTED_DAYS_AHEAD = (7, 30, 60, 90, 180, 365)

    @staticmethod
    def validate(days_ahead: int) -> Tuple[bool, str]:
        if not (ForecastConfigValidator.MIN_DAYS_AHEAD <= days_ahead <= ForecastConfigValidator.MAX_DAYS_AHEAD):
            return False, f"Forecast horizon must be between {ForecastConfigValidator.MIN_DAYS_AHEAD} and {ForecastConfigValidator.MAX_DAYS_AHEAD} days."
        
        return True, ""