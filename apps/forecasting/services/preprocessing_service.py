import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import List, Dict, Tuple, Optional
from django.db.models import Sum, Avg, F, Q
from sales.models import Sales
from forecasting.models import FeatureRegistry


class PreprocessingService:
    """
    Converts raw Sales records into a multivariate time-series DataFrame
    suitable for LSTM training. Designed to be feature-extensible:
    new features are added to FeatureRegistry and implemented here
    without changing the pipeline architecture.
    """
    
    def __init__(self, company_id: int, start_date=None, end_date=None):
        self.company_id = company_id
        self.start_date = start_date
        self.end_date = end_date
        self.features = FeatureRegistry.get_feature_names()
        self.target = FeatureRegistry.get_target_feature()
    
    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    
    def build_training_dataframe(self) -> pd.DataFrame:
        """
        Main entry point. Returns a daily-aggregated DataFrame with
        all engineered features for the company's sales data.
        """
        df = self._aggregate_daily_sales()
        if df.empty:
            return df
        
        df = self._engineer_features(df)
        df = self._handle_missing_values(df)
        df = self._validate_dataframe(df)
        
        return df
    
    def get_feature_matrix(self, df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray, List[str]]:
        """
        Converts the DataFrame into X (features) and y (target) arrays.
        Returns (X, y, feature_names) where X is shape (samples, timesteps, features).
        
        Note: This returns the full sequence. The caller (TrainingService)
        handles the lookback window creation.
        """
        feature_cols = [c for c in self.features if c != self.target]
        
        X = df[feature_cols].values
        y = df[self.target].values
        
        return X, y, feature_cols
    
    # ------------------------------------------------------------------
    # Aggregation
    # ------------------------------------------------------------------
    
    def _aggregate_daily_sales(self) -> pd.DataFrame:
        """
        Aggregate Sales records to daily company-wide totals.
        Returns DataFrame with columns: date, sales_quantity, sales_amount, discount
        """
        queryset = Sales.objects.filter(company_id=self.company_id)
        
        if self.start_date:
            queryset = queryset.filter(date__gte=self.start_date)
        if self.end_date:
            queryset = queryset.filter(date__lte=self.end_date)
        
        # Raw aggregation — Django ORM
        records = queryset.values('date').annotate(
            sales_quantity=Sum('sales_quantity'),
            sales_amount=Sum('sales_amount'),
            discount=Sum('discount')
        ).order_by('date')
        
        if not records:
            return pd.DataFrame(columns=['date'] + self.features)
        
        df = pd.DataFrame(list(records))
        df['date'] = pd.to_datetime(df['date']).dt.date
        df.set_index('date', inplace=True)
        
        # Robust Decimal → float conversion for all numeric columns
        for col in ['sales_quantity', 'sales_amount', 'discount']:
            if col in df.columns:
                df[col] = df[col].apply(self._safe_to_float)
        
        # Ensure all columns exist even if null
        for col in ['sales_quantity', 'sales_amount', 'discount']:
            if col not in df.columns:
                df[col] = 0.0
        
        # Reindex to fill missing days (no-sales days = 0)
        df = self._fill_missing_dates(df)
        
        return df
    
    def _safe_to_float(self, value) -> float:
        """Safely convert any numeric type to float, handling Decimal, None, NaN."""
        if value is None:
            return 0.0
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, (int, float)):
            return float(value)
        if pd.isna(value):
            return 0.0
        try:
            return float(value)
        except (ValueError, TypeError, InvalidOperation):
            return 0.0
    
    def _fill_missing_dates(self, df: pd.DataFrame) -> pd.DataFrame:
        """Ensure continuous daily index with no gaps."""
        if df.empty:
            return df
        
        date_range = pd.date_range(start=df.index.min(), end=df.index.max(), freq='D')
        df = df.reindex(date_range.date, fill_value=0.0)
        df.index.name = 'date'
        
        # Convert index back to date objects for consistency
        df.index = pd.to_datetime(df.index).date
        
        return df
    
    # ------------------------------------------------------------------
    # Feature Engineering
    # ------------------------------------------------------------------
    
    def _engineer_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Apply all registered feature transformations."""
        df = df.copy()
        
        # Ensure numeric types
        df['sales_quantity'] = pd.to_numeric(df['sales_quantity'], errors='coerce').fillna(0)
        df['sales_amount'] = pd.to_numeric(df['sales_amount'], errors='coerce').fillna(0)
        df['discount'] = pd.to_numeric(df['discount'], errors='coerce').fillna(0)
        
        # Temporal features from date index
        df['day_of_week'] = pd.to_datetime(df.index).dayofweek  # 0=Monday
        df['month'] = pd.to_datetime(df.index).month  # 1-12
        df['is_weekend'] = (df['day_of_week'] >= 5).astype(int)
        
        # Cyclic encoding for day_of_week (0-6 -> sin/cos)
        df['day_of_week_sin'] = np.sin(2 * np.pi * df['day_of_week'] / 7)
        df['day_of_week_cos'] = np.cos(2 * np.pi * df['day_of_week'] / 7)
        
        # Cyclic encoding for month (1-12 -> sin/cos)
        df['month_sin'] = np.sin(2 * np.pi * (df['month'] - 1) / 12)
        df['month_cos'] = np.cos(2 * np.pi * (df['month'] - 1) / 12)
        
        # Drop raw cyclical columns, keep only sin/cos pairs
        df.drop(columns=['day_of_week', 'month'], inplace=True)
        
        # Reorder columns to match FeatureRegistry order
        ordered_cols = []
        for feat in self.features:
            if feat in df.columns:
                ordered_cols.append(feat)
        
        # Add any extra engineered columns that aren't in registry
        for col in df.columns:
            if col not in ordered_cols:
                ordered_cols.append(col)
        
        return df[ordered_cols]
    
    # ------------------------------------------------------------------
    # Data Quality
    # ------------------------------------------------------------------
    
    def _handle_missing_values(self, df: pd.DataFrame) -> pd.DataFrame:
        """Forward-fill then backward-fill any remaining NaNs."""
        df = df.ffill().bfill()
        df = df.fillna(0)
        return df
    
    def _validate_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """Ensure no inf values and all numeric."""
        df = df.replace([np.inf, -np.inf], 0)
        df = df.astype(float)
        return df
    
    # ------------------------------------------------------------------
    # Sequence Builder (for LSTM lookback windows)
    # ------------------------------------------------------------------
    
    @staticmethod
    def create_sequences(
        data: np.ndarray,
        target_idx: int,
        lookback: int = 30
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Create LSTM sequences from a 2D array.
        
        Args:
            data: 2D array shape (timesteps, features)
            target_idx: index of the target column within data
            lookback: number of past timesteps to use as input
        
        Returns:
            X: shape (samples, lookback, features)
            y: shape (samples,)
        """
        X, y = [], []
        for i in range(lookback, len(data)):
            X.append(data[i - lookback:i])
            y.append(data[i, target_idx])
        
        return np.array(X), np.array(y)