import os
import numpy as np
import pandas as pd
from datetime import datetime, timedelta, date
from typing import List, Dict, Optional, Tuple
from decimal import Decimal
from django.db import transaction
from django.db.models import Avg, Sum
from django.conf import settings
from tensorflow import keras
from tensorflow.keras.layers import Dropout

from forecasting.models import ForecastModel, ForecastResult, FeatureRegistry
from forecasting.services.preprocessing_service import PreprocessingService
from sales.models import Sales


class ForecastService:
    """
    Generate future sales forecasts with business intelligence.
    """

    # Default gross margin used when no direct cost data is available.
    # This ensures Expected Profit always has a meaningful value.
    # When real procurement cost data exists, it takes priority automatically.
    DEFAULT_GROSS_MARGIN = Decimal('0.30')

    def __init__(self, company_id: int):
        self.company_id = company_id
        self.model = None
        self.scaler = None
        self.config = None
        self.feature_names = None
        self.target_name = FeatureRegistry.get_target_feature()
        self.has_dropout = False

    def forecast(
        self,
        days_ahead: int = settings.FORECAST_DEFAULT_HORIZON,
        model_id: Optional[int] = None,
        include_confidence: bool = True
    ) -> Dict:
        forecast_model = self._load_model(model_id)
        if not forecast_model:
            return {'success': False, 'error': 'No active forecast model found for this company.'}

        self.config = forecast_model.architecture
        lookback = self.config.get('lookback', 30)
        df = self._build_recent_window(lookback)

        if df.empty or len(df) < lookback:
            return {'success': False, 'error': f'Insufficient recent data. Need {lookback} days, found {len(df)}.'}

        scaled_window = self.scaler.transform(df.values)

        predictions, lower_bounds, upper_bounds = self._predict_sequence(
            scaled_window, days_ahead, include_confidence, df.index[-1]
        )

        last_date = df.index[-1]
        forecast_dates = [last_date + timedelta(days=i + 1) for i in range(days_ahead)]

        # Calculate business intelligence
        business_metrics = self._calculate_business_metrics()

        results = self._store_results(
            forecast_model, forecast_dates, predictions,
            lower_bounds if include_confidence else None,
            upper_bounds if include_confidence else None,
            df, business_metrics
        )

        return {
            'success': True, 'model_id': forecast_model.id, 'forecasts': results,
            'dates': forecast_dates, 'predictions': predictions,
            'lower_bounds': lower_bounds if include_confidence else None,
            'upper_bounds': upper_bounds if include_confidence else None,
        }

    def _load_model(self, model_id: Optional[int]) -> Optional[ForecastModel]:
        if model_id:
            try:
                forecast_model = ForecastModel.objects.get(id=model_id, company_id=self.company_id)
            except ForecastModel.DoesNotExist:
                return None
        else:
            forecast_model = ForecastModel.objects.filter(
                company_id=self.company_id, is_active=True, is_company_wide=True
            ).first()

        if not forecast_model or not forecast_model.model_path:
            return None
        if not os.path.exists(forecast_model.model_path):
            return None

        self.model = keras.models.load_model(forecast_model.model_path)
        self.scaler = self._deserialize_scaler(forecast_model.scaler_config)
        self.feature_names = [f['name'] for f in forecast_model.feature_config]

        has_dropout_layers = any(isinstance(layer, Dropout) for layer in self.model.layers)
        dropout_rate = forecast_model.architecture.get('dropout_rate', 0)
        self.has_dropout = has_dropout_layers and (dropout_rate > 0)

        return forecast_model

    def _deserialize_scaler(self, scaler_config: Dict):
        from sklearn.preprocessing import MinMaxScaler
        scaler = MinMaxScaler(feature_range=tuple(scaler_config['feature_range']))
        scaler.min_ = np.array(scaler_config['min_'])
        scaler.scale_ = np.array(scaler_config['scale_'])
        scaler.data_min_ = np.array(scaler_config['data_min_'])
        scaler.data_max_ = np.array(scaler_config['data_max_'])
        scaler.data_range_ = np.array(scaler_config['data_range_'])
        scaler.n_features_in_ = scaler_config['n_features_in_']
        scaler.n_samples_seen_ = scaler_config['n_samples_seen_']
        return scaler

    def _build_recent_window(self, lookback: int) -> pd.DataFrame:
        latest_sale = Sales.objects.filter(company_id=self.company_id).order_by('-date').values_list('date', flat=True).first()
        if latest_sale is None:
            return pd.DataFrame()

        # Anchor the forecast to the last observed sale, not to today.  This
        # avoids creating zero-filled pseudo-history when uploaded data ends
        # before the current calendar date.
        end_date = latest_sale
        buffer_days = max(15, int(lookback * 0.5))
        start_date = end_date - timedelta(days=lookback + buffer_days)

        preprocessor = PreprocessingService(
            company_id=self.company_id, start_date=start_date, end_date=end_date
        )
        df = preprocessor.build_training_dataframe()
        if len(df) < lookback:
            return df
        return df.tail(lookback)

    def _predict_sequence(
        self, scaled_window: np.ndarray, days_ahead: int, include_confidence: bool,
        last_observed_date: date,
    ) -> Tuple[List[float], Optional[List[float]], Optional[List[float]]]:
        predictions = []
        lower_bounds = [] if include_confidence else None
        upper_bounds = [] if include_confidence else None

        current_window = scaled_window.copy()
        target_idx = self.feature_names.index(self.target_name)
        confidence_margin = 0.10

        for day in range(days_ahead):
            X = current_window.reshape(1, current_window.shape[0], current_window.shape[1])

            if include_confidence and self.has_dropout:
                mc_samples = []
                for _ in range(50):
                    pred = self.model(X, training=True).numpy().flatten()[0]
                    mc_samples.append(pred)
                mean_pred = float(np.mean(mc_samples))
                std_pred = float(np.std(mc_samples))
                predictions.append(mean_pred)
                lower_bounds.append(mean_pred - 1.96 * std_pred)
                upper_bounds.append(mean_pred + 1.96 * std_pred)
            else:
                pred = self.model.predict(X, verbose=0).flatten()[0]
                predictions.append(float(pred))
                if include_confidence:
                    lower_bounds.append(pred * (1 - confidence_margin))
                    upper_bounds.append(pred * (1 + confidence_margin))

            next_row = current_window[-1].copy()
            next_row[target_idx] = predictions[-1]
            next_row = self._update_temporal_features(next_row, last_observed_date, day + 1)
            current_window = np.vstack([current_window[1:], next_row])

        inv_predictions = self._inverse_transform_target(np.array(predictions))

        if include_confidence:
            inv_lower = self._inverse_transform_target(np.array(lower_bounds))
            inv_upper = self._inverse_transform_target(np.array(upper_bounds))
            return inv_predictions.tolist(), inv_lower.tolist(), inv_upper.tolist()
        else:
            return inv_predictions.tolist(), None, None

    def _update_temporal_features(
        self, row: np.ndarray, last_observed_date: date, days_ahead: int
    ) -> np.ndarray:
        future_date = last_observed_date + timedelta(days=days_ahead)
        dow = future_date.weekday()
        month = future_date.month
        is_weekend = 1 if dow >= 5 else 0

        if 'day_of_week_sin' in self.feature_names:
            row[self.feature_names.index('day_of_week_sin')] = np.sin(2 * np.pi * dow / 7)
        if 'day_of_week_cos' in self.feature_names:
            row[self.feature_names.index('day_of_week_cos')] = np.cos(2 * np.pi * dow / 7)
        if 'month_sin' in self.feature_names:
            row[self.feature_names.index('month_sin')] = np.sin(2 * np.pi * (month - 1) / 12)
        if 'month_cos' in self.feature_names:
            row[self.feature_names.index('month_cos')] = np.cos(2 * np.pi * (month - 1) / 12)
        if 'is_weekend' in self.feature_names:
            row[self.feature_names.index('is_weekend')] = float(is_weekend)
        return row

    def _inverse_transform_target(self, scaled_values: np.ndarray) -> np.ndarray:
        target_idx = self.feature_names.index(self.target_name)
        dummy = np.zeros((len(scaled_values), self.scaler.n_features_in_))
        dummy[:, target_idx] = scaled_values
        inv = self.scaler.inverse_transform(dummy)
        return inv[:, target_idx]

    def _calculate_business_metrics(self) -> Dict:
        """
        Calculate average selling price, cost price, and historical revenue.

        Cost price resolution order:
          1. PurchaseHistory weighted average (most accurate)
          2. PurchaseOrderItem weighted average
          3. Product.cost_price average
          4. Estimated from selling price using default gross margin (fallback)

        The fallback ensures Expected Profit is NEVER None/blank.
        When real procurement data becomes available, it automatically takes priority.
        """
        from inventory.models import Product

        # ------------------------------------------------------------------
        # 1. Average Selling Price (weighted from last 90 days of sales)
        # ------------------------------------------------------------------
        ninety_days_ago = date.today() - timedelta(days=90)
        sales_agg = Sales.objects.filter(
            company_id=self.company_id,
            date__gte=ninety_days_ago
        ).aggregate(
            total_qty=Sum('sales_quantity'),
            total_amt=Sum('sales_amount')
        )

        avg_selling_price = Decimal('0.00')
        if sales_agg['total_qty'] and sales_agg['total_amt'] and sales_agg['total_qty'] > 0:
            avg_selling_price = Decimal(str(sales_agg['total_amt'])) / Decimal(str(sales_agg['total_qty']))
        else:
            # Fallback to Product.base_price average
            products = Product.objects.filter(company_id=self.company_id, base_price__gt=0)
            if products.exists():
                avg_base = products.aggregate(avg=Avg('base_price'))['avg']
                if avg_base:
                    avg_selling_price = Decimal(str(avg_base))

        # ------------------------------------------------------------------
        # 2. Average Cost Price (4-source fallback chain)
        # ------------------------------------------------------------------
        avg_cost_price = Decimal('0.00')
        cost_source = 'none'

        # Source A: PurchaseHistory (most accurate — weighted avg from completed purchases)
        try:
            from procurement.models import PurchaseHistory
            ph_agg = PurchaseHistory.objects.filter(company_id=self.company_id).aggregate(
                total_qty=Sum('quantity'),
                total_cost=Sum('total_cost')
            )
            if ph_agg['total_qty'] and ph_agg['total_cost'] and ph_agg['total_qty'] > 0:
                avg_cost_price = Decimal(str(ph_agg['total_cost'])) / Decimal(str(ph_agg['total_qty']))
                cost_source = 'purchase_history'
        except Exception:
            pass

        # Source B: PurchaseOrderItem (weighted avg from purchase orders)
        if avg_cost_price == Decimal('0.00'):
            try:
                from procurement.models import PurchaseOrderItem
                poi_agg = PurchaseOrderItem.objects.filter(
                    purchase_order__company_id=self.company_id
                ).aggregate(
                    total_qty=Sum('quantity_ordered'),
                    total_cost=Sum('total_cost')
                )
                if poi_agg['total_qty'] and poi_agg['total_cost'] and poi_agg['total_qty'] > 0:
                    avg_cost_price = Decimal(str(poi_agg['total_cost'])) / Decimal(str(poi_agg['total_qty']))
                    cost_source = 'purchase_orders'
            except Exception:
                pass

        # Source C: Product.cost_price (from inventory product profiles)
        if avg_cost_price == Decimal('0.00'):
            products_with_cost = Product.objects.filter(
                company_id=self.company_id,
                cost_price__isnull=False,
                cost_price__gt=0
            )
            if products_with_cost.exists():
                avg_cost = products_with_cost.aggregate(avg=Avg('cost_price'))['avg']
                if avg_cost:
                    avg_cost_price = Decimal(str(avg_cost))
                    cost_source = 'product_cost_price'

        # Source D: Estimated from selling price using default gross margin
        # This ensures Expected Profit is NEVER blank/None
        if avg_cost_price == Decimal('0.00') and avg_selling_price > Decimal('0.00'):
            avg_cost_price = avg_selling_price * (Decimal('1') - self.DEFAULT_GROSS_MARGIN)
            cost_source = 'estimated_margin'

        # ------------------------------------------------------------------
        # 3. Historical average daily revenue (last 30 days)
        # ------------------------------------------------------------------
        thirty_days_ago = date.today() - timedelta(days=30)
        historical_revenue = Sales.objects.filter(
            company_id=self.company_id,
            date__gte=thirty_days_ago
        ).aggregate(total=Sum('sales_amount'))['total']

        historical_avg_revenue = Decimal('0.00')
        if historical_revenue:
            historical_avg_revenue = Decimal(str(historical_revenue)) / Decimal('30')

        return {
            'average_selling_price': avg_selling_price,
            'average_cost_price': avg_cost_price,
            'historical_avg_revenue': historical_avg_revenue,
            'cost_source': cost_source,
        }

    def _store_results(
        self, forecast_model: ForecastModel, dates: List[date],
        predictions: List[float], lower_bounds: Optional[List[float]],
        upper_bounds: Optional[List[float]], input_df: pd.DataFrame,
        business_metrics: Dict
    ) -> List[ForecastResult]:
        with transaction.atomic():
            ForecastResult.objects.filter(forecast_model=forecast_model).delete()

            results = []
            avg_price = business_metrics['average_selling_price']
            avg_cost = business_metrics['average_cost_price']
            hist_revenue = business_metrics['historical_avg_revenue']

            for i, forecast_date in enumerate(dates):
                qty = round(predictions[i], 2)
                expected_revenue = Decimal(str(qty)) * avg_price

                # Calculate profit — avg_cost is now guaranteed > 0
                # thanks to the estimated margin fallback in _calculate_business_metrics
                expected_profit = None
                if avg_cost > Decimal('0.00'):
                    expected_profit = (avg_price - avg_cost) * Decimal(str(qty))

                result = ForecastResult.objects.create(
                    company_id=self.company_id,
                    forecast_model=forecast_model,
                    forecast_date=forecast_date,
                    forecast_horizon=len(dates),
                    predicted_quantity=qty,
                    lower_bound=round(lower_bounds[i], 2) if lower_bounds is not None else None,
                    upper_bound=round(upper_bounds[i], 2) if upper_bounds is not None else None,
                    average_selling_price=avg_price,
                    expected_revenue=expected_revenue,
                    expected_profit=expected_profit,
                    historical_avg_revenue=hist_revenue,
                    input_features={
                        'last_known_date': str(input_df.index[-1]),
                        'last_known_quantity': float(input_df[self.target_name].iloc[-1]),
                        'prediction_day': i + 1,
                        'cost_source': business_metrics.get('cost_source', 'unknown'),
                    }
                )
                results.append(result)

            return results
