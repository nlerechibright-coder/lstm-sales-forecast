import os
import logging
from celery import shared_task
from django.conf import settings

from accounts.models import Company
from forecasting.services.training_service import TrainingService
from forecasting.services.forecast_service import ForecastService
from forecasting.services.progress_tracker import update_run_progress, clear_run_progress
from forecasting.models import ForecastRun
from forecasting.services.task_runner import run_task

logger = logging.getLogger(__name__)


@shared_task(
    bind=True, max_retries=3, default_retry_delay=60,
    autoretry_for=(Exception,), retry_backoff=True,
    retry_backoff_max=600, retry_jitter=True,
)
def train_forecast_model(self, company_id: int, run_id: int = None, config: dict = None):
    logger.info(f"[TrainTask] Starting model training for company {company_id}, run {run_id}")
    
    if run_id and config:
        update_run_progress(run_id, 0, config.get('epochs', 100), 'Initializing training pipeline...')
    
    try:
        service = TrainingService(company_id=company_id, config=config)
        result = service.train(run_id=run_id)
        
        logger.info(
            f"[TrainTask] Training completed for company {company_id}. "
            f"Model v{result['version']}, MAE={result['mae']:.4f}, RMSE={result['rmse']:.4f}"
        )
        
        return {
            'status': 'success', 'model_id': result['model_id'], 'version': result['version'],
            'mae': result['mae'], 'rmse': result['rmse'], 'mape': result['mape'],
            'epochs_trained': result['epochs_trained'], 'training_samples': result['training_samples'],
        }
        
    except Exception as exc:
        logger.error(f"[TrainTask] Training failed for company {company_id}: {exc}")
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=2, default_retry_delay=30, autoretry_for=(Exception,))
def generate_forecast(
    self, company_id: int, days_ahead: int = settings.FORECAST_DEFAULT_HORIZON, model_id: int = None
):
    logger.info(f"[ForecastTask] Generating {days_ahead}-day forecast for company {company_id}")
    
    try:
        service = ForecastService(company_id=company_id)
        result = service.forecast(days_ahead=days_ahead, model_id=model_id, include_confidence=True)
        
        if result['success']:
            logger.info(
                f"[ForecastTask] Forecast generated for company {company_id}. "
                f"Model {result['model_id']}, {len(result['predictions'])} days predicted."
            )
            return {
                'status': 'success', 'model_id': result['model_id'], 'days_ahead': days_ahead,
                'predictions': result['predictions'], 'dates': [str(d) for d in result['dates']],
            }
        else:
            logger.warning(f"[ForecastTask] Forecast failed: {result.get('error')}")
            return {'status': 'failed', 'error': result.get('error')}
            
    except Exception as exc:
        logger.error(f"[ForecastTask] Forecast generation failed for company {company_id}: {exc}")
        raise self.retry(exc=exc)


@shared_task
def trigger_retraining_check(company_id: int):
    """Check whether enough new sales data exists for a retraining cycle."""
    status = TrainingService.get_retraining_status(company_id=company_id)
    if not status['should_retrain']:
        logger.info(f"[RetrainCheck] Company {company_id} does not qualify: {status['reason']}")
        return {'status': 'skipped', 'reason': status['reason']}

    existing_run = ForecastRun.objects.filter(
        company_id=company_id,
        status__in=['PENDING', 'RUNNING']
    ).first()
    if existing_run:
        logger.info(f"[RetrainCheck] Company {company_id} already has a training run in progress: #{existing_run.id}")
        return {'status': 'skipped', 'reason': 'training_in_progress'}

    run = ForecastRun.objects.create(
        company_id=company_id,
        run_type='AUTO_RETRAIN',
        status='PENDING',
    )

    outcome = run_task(train_forecast_model, company_id, run.id, {})
    return {
        'status': 'queued' if outcome.get('async') else 'sync_run',
        'run_id': run.id,
        'reason': status['reason'],
    }


@shared_task
def auto_retrain_all_companies():
    """Periodic task (Celery Beat) to auto-retrain models when new data qualifies."""
    company_ids = list(Company.objects.filter(sales_records__isnull=False).values_list('id', flat=True).distinct())
    results = []
    for company_id in company_ids:
        results.append(trigger_retraining_check.delay(company_id) if hasattr(trigger_retraining_check, 'delay') else trigger_retraining_check(company_id))
    return {'company_count': len(company_ids), 'triggered': len(results)}
