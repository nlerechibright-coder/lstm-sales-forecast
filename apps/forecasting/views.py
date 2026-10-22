from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse, HttpResponseForbidden
from django.views.decorators.http import require_POST
from django.db.models import Sum, Q, Count, Max, Avg, Min
from django.core.paginator import Paginator
from django.contrib import messages
from forecasting.models import ForecastModel, ForecastRun, ForecastResult
from forecasting.services.training_service import TrainingService
from forecasting.services.forecast_service import ForecastService
from forecasting.services.task_runner import run_task
from forecasting.services.validation_service import TrainingConfigValidator, ForecastConfigValidator
from forecasting.services.progress_tracker import get_run_progress
from forecasting.tasks import train_forecast_model, generate_forecast
from sales.models import Sales, DataImport
from core.models import UploadJob
import csv
from datetime import datetime, timedelta


def _check_forecasting_permission(user):
    """Only Owner and Manager can access forecasting/AI features."""
    return user.role in ['owner', 'manager']


@login_required
def training_dashboard(request):
    """Main dashboard for the ML training pipeline. Restricted to Owner/Manager."""
    if not _check_forecasting_permission(request.user):
        return HttpResponseForbidden("Access denied. Only Owners and Managers can access AI Forecasting.")

    company = request.user.company

    active_model = ForecastModel.objects.filter(
        company=company, is_active=True, is_company_wide=True
    ).select_related('company').first()

    runs = ForecastRun.objects.filter(company=company).order_by('-created_at')[:10]

    current_run = ForecastRun.objects.filter(
        company=company, status__in=['PENDING', 'RUNNING']
    ).first()

    recent_forecasts = ForecastResult.objects.filter(
        company=company, forecast_model__is_active=True
    ).select_related('forecast_model').order_by('-forecast_date')[:14]

    total_sales_days = Sales.objects.filter(company=company).values('date').distinct().count()
    latest_sale = Sales.objects.filter(company=company).order_by('-date').first()
    earliest_sale = Sales.objects.filter(company=company).order_by('date').first()

    latest_run = ForecastRun.objects.filter(
        company=company, status='COMPLETED'
    ).order_by('-completed_at').first()
    latest_mae = latest_run.mae if latest_run else None
    latest_rmse = latest_run.rmse if latest_run else None
    latest_mape = latest_run.mape if latest_run else None

    models_qs = ForecastModel.objects.filter(
        company=company, is_company_wide=True
    ).order_by('version')
    
    model_history = []
    for model in models_qs:
        model_latest_run = model.runs.filter(status='COMPLETED').order_by('-completed_at').first()
        model_history.append({
            'version': model.version,
            'trained_at': model.trained_at.isoformat() if model.trained_at else None,
            'validation_loss': model.validation_loss,
            'training_loss': model.training_loss,
            'training_samples': model.training_samples,
            'mae': model_latest_run.mae if model_latest_run else None,
            'rmse': model_latest_run.rmse if model_latest_run else None,
            'mape': model_latest_run.mape if model_latest_run else None,
        })

    latest_upload = UploadJob.objects.filter(company=company).order_by('-created_at').first()
    upload_summary = None
    if latest_upload:
        record_count = DataImport.objects.filter(upload_job=latest_upload).count()
        upload_summary = {
            'last_upload_date': latest_upload.created_at,
            'record_count': record_count,
            'status': latest_upload.get_status_display(),
            'status_raw': latest_upload.status,
            'job_id': latest_upload.id,
            'filename': latest_upload.file.name.split('/')[-1] if latest_upload.file else 'Unknown',
        }

    return render(request, 'forecasting/training_dashboard.html', {
        'active_model': active_model, 
        'runs': runs, 
        'current_run': current_run,
        'recent_forecasts': recent_forecasts, 
        'total_sales_days': total_sales_days,
        'latest_sale': latest_sale, 
        'earliest_sale': earliest_sale,
        'model_history': model_history, 
        'has_enough_data': total_sales_days >= 7,  # <-- CHANGED FROM 60 TO 7
        'upload_summary': upload_summary,
        'latest_mae': latest_mae,
        'latest_rmse': latest_rmse,
        'latest_mape': latest_mape,
        'forecast_horizon_options': ForecastConfigValidator.SUPPORTED_DAYS_AHEAD,
        'default_forecast_horizon': ForecastConfigValidator.DEFAULT_DAYS_AHEAD,
    })


@login_required
def training_diagnose(request):
    """Diagnostic endpoint. Restricted to Owner/Manager."""
    if not _check_forecasting_permission(request.user):
        return JsonResponse({'error': 'Access denied'}, status=403)

    company = request.user.company
    
    total_sales_days = Sales.objects.filter(company=company).values('date').distinct().count()
    total_records = Sales.objects.filter(company=company).count()
    
    current_run = ForecastRun.objects.filter(
        company=company, status__in=['PENDING', 'RUNNING']
    ).first()
    
    active_model = ForecastModel.objects.filter(
        company=company, is_active=True, is_company_wide=True
    ).first()
    
    latest_upload = UploadJob.objects.filter(company=company).order_by('-created_at').first()
    
    return JsonResponse({
        'total_sales_days': total_sales_days, 'total_sales_records': total_records,
        'has_enough_data': total_sales_days >= 7,  # <-- CHANGED FROM 60 TO 7
        'current_run_id': current_run.id if current_run else None,
        'current_run_status': current_run.status if current_run else None,
        'active_model_id': active_model.id if active_model else None,
        'active_model_version': active_model.version if active_model else None,
        'latest_upload_id': latest_upload.id if latest_upload else None,
        'latest_upload_status': latest_upload.status if latest_upload else None,
        'button_disabled_reason': _get_disabled_reason(company, total_sales_days, current_run),
    })


def _get_disabled_reason(company, total_sales_days, current_run):
    """Determine why the train button is disabled."""
    if current_run:
        return f"A training job (#{current_run.id}) is already {current_run.status.lower()}"
    if total_sales_days < 7:  # <-- CHANGED FROM 60 TO 7
        return f"Need at least 7 days of data. Currently have {total_sales_days} days."
    return None


@login_required
@require_POST
def trigger_training(request):
    """Trigger model training via task runner. Restricted to Owner/Manager."""
    if not _check_forecasting_permission(request.user):
        return JsonResponse({'success': False, 'error': 'Access denied. Only Owners and Managers can train models.'}, status=403)

    company = request.user.company

    running = ForecastRun.objects.filter(
        company=company, status__in=['PENDING', 'RUNNING']
    ).exists()

    if running:
        return JsonResponse({'success': False, 'error': 'A training job is already in progress for this company.'})

    config = {}
    try:
        if request.POST.get('lookback'):
            config['lookback'] = int(request.POST.get('lookback'))
        if request.POST.get('epochs'):
            config['epochs'] = int(request.POST.get('epochs'))
        if request.POST.get('lstm_units'):
            config['lstm_units'] = int(request.POST.get('lstm_units'))
    except ValueError:
        return JsonResponse({'success': False, 'error': 'Invalid parameter format. Numbers expected.'})

    is_valid, error_msg = TrainingConfigValidator.validate(config)
    if not is_valid:
        return JsonResponse({'success': False, 'error': error_msg})

    run = ForecastRun.objects.create(company=company, run_type='TRAIN', status='PENDING')

    try:
        outcome = run_task(train_forecast_model, company.id, run.id, config)

        if outcome['async']:
            messages.info(request, f'Training job #{run.id} queued. You will be notified when complete.')
            return JsonResponse({'success': True, 'run_id': run.id, 'message': outcome['message']})
        else:
            messages.success(request, f'Training job #{run.id} completed successfully!')
            return JsonResponse({'success': True, 'run_id': run.id, 'message': outcome['message'], 'sync': True})
    except Exception as e:
        messages.error(request, f'Training failed: {str(e)}')
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
def training_status(request, run_id):
    """AJAX endpoint to check training progress. Restricted to Owner/Manager."""
    if not _check_forecasting_permission(request.user):
        return JsonResponse({'error': 'Access denied'}, status=403)

    run = get_object_or_404(ForecastRun, id=run_id, company=request.user.company)

    response_data = {
        'status': run.status, 'run_type': run.run_type, 'total_records': run.total_records,
        'mae': run.mae, 'rmse': run.rmse, 'mape': run.mape, 'error_message': run.error_message,
        'created_at': run.created_at.isoformat(),
        'started_at': run.started_at.isoformat() if run.started_at else None,
        'completed_at': run.completed_at.isoformat() if run.completed_at else None,
        'duration': run.duration_display,
    }

    if run.status == 'RUNNING':
        response_data['progress'] = get_run_progress(run.id)

    return JsonResponse(response_data)


@login_required
def training_logs(request, run_id):
    """View full training logs for a run. Restricted to Owner/Manager."""
    if not _check_forecasting_permission(request.user):
        return JsonResponse({'error': 'Access denied'}, status=403)

    run = get_object_or_404(ForecastRun, id=run_id, company=request.user.company)
    
    return JsonResponse({
        'run_id': run.id, 'status': run.status, 'logs': run.training_log or 'No logs available',
    })


@login_required
def forecast_results(request):
    """Professional Forecast Results Dashboard. Restricted to Owner/Manager."""
    if not _check_forecasting_permission(request.user):
        return HttpResponseForbidden("Access denied. Only Owners and Managers can view Forecast Results.")

    company = request.user.company

    active_model = ForecastModel.objects.filter(
        company=company, is_active=True, is_company_wide=True
    ).first()

    forecasts = []
    actuals = {}
    stats = {}
    ai_recommendation = {}
    trend_info = {}

    if active_model:
        forecast_qs = ForecastResult.objects.filter(
            forecast_model=active_model
        ).order_by('forecast_date')

        forecasts = [
            {
                'forecast_date': str(f.forecast_date),
                'predicted_quantity': f.predicted_quantity,
                'lower_bound': f.lower_bound,
                'upper_bound': f.upper_bound,
                'actual_quantity': f.actual_quantity,
                'confidence_percentage': f.confidence_percentage,
                'average_selling_price': float(f.average_selling_price) if f.average_selling_price is not None else 0.0,
                'expected_revenue': float(f.expected_revenue) if f.expected_revenue is not None else 0.0,
                'expected_profit': float(f.expected_profit) if f.expected_profit is not None else None,
                'historical_avg_revenue': float(f.historical_avg_revenue) if f.historical_avg_revenue is not None else 0.0,
                'revenue_difference': f.revenue_difference,
                'revenue_percentage_change': f.revenue_percentage_change,
            }
            for f in forecast_qs
        ]

        if forecasts:
            quantities = [f['predicted_quantity'] for f in forecasts]
            revenues = [f['expected_revenue'] for f in forecasts]
            profits = [f['expected_profit'] for f in forecasts if f['expected_profit'] is not None]
            
            stats = {
                'total': round(sum(quantities), 2),
                'avg': round(sum(quantities) / len(quantities), 2),
                'max': round(max(quantities), 2),
                'min': round(min(quantities), 2),
                'count': len(quantities),
                'model_version': active_model.version,
                'generated_at': active_model.trained_at.strftime('%B %d, %Y at %I:%M %p') if active_model.trained_at else 'Unknown',
                'forecast_horizon': forecast_qs.first().forecast_horizon if forecast_qs.exists() else 7,
                'total_revenue': round(sum(revenues), 2),
                'avg_daily_revenue': round(sum(revenues) / len(revenues), 2) if revenues else 0,
                'max_revenue': round(max(revenues), 2) if revenues else 0,
                'min_revenue': round(min(revenues), 2) if revenues else 0,
                'total_profit': round(sum(profits), 2) if profits else None,
                'avg_selling_price': forecasts[0]['average_selling_price'] if forecasts else 0,
            }

            if len(quantities) >= 2:
                first_half_avg = sum(quantities[:len(quantities)//2]) / (len(quantities)//2)
                second_half_avg = sum(quantities[len(quantities)//2:]) / (len(quantities) - len(quantities)//2)
                trend_percentage = ((second_half_avg - first_half_avg) / first_half_avg * 100) if first_half_avg > 0 else 0
                
                if trend_percentage > 5:
                    trend_info = {
                        'direction': 'increasing',
                        'icon': '📈',
                        'text': 'Increasing Demand',
                        'percentage': round(trend_percentage, 1),
                        'color': 'success'
                    }
                elif trend_percentage < -5:
                    trend_info = {
                        'direction': 'decreasing',
                        'icon': '📉',
                        'text': 'Decreasing Demand',
                        'percentage': round(abs(trend_percentage), 1),
                        'color': 'danger'
                    }
                else:
                    trend_info = {
                        'direction': 'stable',
                        'icon': '➖',
                        'text': 'Stable Demand',
                        'percentage': round(abs(trend_percentage), 1),
                        'color': 'info'
                    }

            if trend_info:
                if trend_info['direction'] == 'decreasing':
                    ai_recommendation = {
                        'title': 'Demand Decline Detected',
                        'description': f"Demand is forecast to decline by approximately {trend_info['percentage']}% over the next {stats['count']} days.",
                        'actions': [
                            'Reduce restocking quantities',
                            'Avoid excess inventory buildup',
                            'Consider promotional campaigns to boost sales',
                            'Review pricing strategy'
                        ],
                        'priority': 'medium',
                        'icon': '⚠️'
                    }
                elif trend_info['direction'] == 'increasing':
                    ai_recommendation = {
                        'title': 'Demand Growth Opportunity',
                        'description': f"Demand is forecast to increase by approximately {trend_info['percentage']}% over the next {stats['count']} days.",
                        'actions': [
                            'Increase inventory levels',
                            'Ensure adequate staffing',
                            'Consider bulk purchasing for better margins',
                            'Prepare for higher sales volume'
                        ],
                        'priority': 'high',
                        'icon': '🚀'
                    }
                else:
                    ai_recommendation = {
                        'title': 'Stable Demand Forecast',
                        'description': f"Demand is expected to remain stable over the next {stats['count']} days.",
                        'actions': [
                            'Maintain current inventory levels',
                            'Continue regular operations',
                            'Monitor for any sudden changes',
                            'Focus on operational efficiency'
                        ],
                        'priority': 'low',
                        'icon': '✓'
                    }

            start_date = forecast_qs.first().forecast_date
            end_date = forecast_qs.last().forecast_date

            actual_sales = Sales.objects.filter(
                company=company, date__gte=start_date, date__lte=end_date
            ).values('date').annotate(
                total_quantity=Sum('sales_quantity')
            ).order_by('date')

            actuals = {str(a['date']): float(a['total_quantity']) for a in actual_sales}

    return render(request, 'forecasting/forecast_results.html', {
        'active_model': active_model, 
        'forecasts': forecasts, 
        'actuals': actuals,
        'has_forecasts': len(forecasts) > 0, 
        'stats': stats,
        'ai_recommendation': ai_recommendation,
        'trend_info': trend_info,
    })


@login_required
@require_POST
def trigger_forecast(request):
    """Trigger forecast generation. Restricted to Owner/Manager."""
    if not _check_forecasting_permission(request.user):
        return JsonResponse({'success': False, 'error': 'Access denied. Only Owners and Managers can generate forecasts.'}, status=403)

    company = request.user.company

    try:
        days_ahead = int(request.POST.get('days_ahead', ForecastConfigValidator.DEFAULT_DAYS_AHEAD))
    except ValueError:
        return JsonResponse({'success': False, 'error': 'Days ahead must be a number.'})

    is_valid, error_msg = ForecastConfigValidator.validate(days_ahead)
    if not is_valid:
        return JsonResponse({'success': False, 'error': error_msg})

    active_model = ForecastModel.objects.filter(
        company=company, is_active=True, is_company_wide=True
    ).first()

    if not active_model:
        return JsonResponse({'success': False, 'error': 'No trained model found. Please train a model first.'})

    try:
        outcome = run_task(generate_forecast, company.id, days_ahead)

        if outcome['async']:
            return JsonResponse({'success': True, 'message': f'{days_ahead}-day forecast queued.'})
        else:
            return JsonResponse({'success': True, 'message': f'{days_ahead}-day forecast generated.', 'sync': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
def forecast_history(request):
    """Paginated list of all forecast history. Restricted to Owner/Manager."""
    if not _check_forecasting_permission(request.user):
        return HttpResponseForbidden("Access denied.")

    company = request.user.company

    queryset = ForecastResult.objects.filter(
        company=company
    ).select_related('forecast_model').order_by('-created_at', '-forecast_date')

    search_query = request.GET.get('q', '').strip()
    if search_query:
        queryset = queryset.filter(
            Q(forecast_model__name__icontains=search_query) |
            Q(forecast_date__icontains=search_query)
        )

    model_filter = request.GET.get('model', '')
    if model_filter and model_filter != 'all':
        try:
            queryset = queryset.filter(forecast_model_id=int(model_filter))
        except (ValueError, TypeError):
            pass

    status_filter = request.GET.get('status', '')
    if status_filter == 'verified':
        queryset = queryset.filter(actual_quantity__isnull=False)
    elif status_filter == 'pending':
        queryset = queryset.filter(actual_quantity__isnull=True)

    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    if date_from:
        try:
            queryset = queryset.filter(forecast_date__gte=datetime.strptime(date_from, '%Y-%m-%d').date())
        except ValueError:
            pass
    if date_to:
        try:
            queryset = queryset.filter(forecast_date__lte=datetime.strptime(date_to, '%Y-%m-%d').date())
        except ValueError:
            pass

    paginator = Paginator(queryset, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    all_models = ForecastModel.objects.filter(
        company=company, is_company_wide=True
    ).order_by('-version')

    context = {
        'page_obj': page_obj, 'search_query': search_query, 'model_filter': model_filter,
        'status_filter': status_filter, 'date_from': date_from, 'date_to': date_to,
        'all_models': all_models, 'total_forecasts': queryset.count(),
    }

    return render(request, 'forecasting/forecast_history.html', context)


@login_required
def forecast_detail(request, forecast_id):
    """Detailed view of a single forecast result. Restricted to Owner/Manager."""
    if not _check_forecasting_permission(request.user):
        return HttpResponseForbidden("Access denied.")

    company = request.user.company

    forecast = get_object_or_404(
        ForecastResult, id=forecast_id, company=company
    )

    model = forecast.forecast_model

    historical_sales = Sales.objects.filter(
        company=company, date__lt=forecast.forecast_date
    ).order_by('-date')[:30]

    historical_data = []
    if historical_sales.exists():
        historical_data = [
            {
                'date': str(s.date),
                'quantity': s.sales_quantity
            }
            for s in historical_sales
        ]
        historical_data.reverse()

    historical_avg = 0
    if historical_sales.exists():
        total_qty = sum(s.sales_quantity for s in historical_sales)
        historical_avg = total_qty / historical_sales.count()

    confidence = forecast.confidence_percentage

    difference = None
    percentage_change = None
    if historical_avg > 0:
        difference = forecast.predicted_quantity - historical_avg
        percentage_change = (difference / historical_avg) * 100

    error = None
    error_percent = None
    if forecast.actual_quantity is not None and forecast.actual_quantity > 0:
        error = forecast.predicted_quantity - forecast.actual_quantity
        error_percent = (error / forecast.actual_quantity) * 100

    forecast_status = 'pending'
    if forecast.actual_quantity is not None:
        forecast_status = 'verified'
    elif forecast.forecast_date < datetime.now().date():
        forecast_status = 'overdue'

    context = {
        'forecast': forecast, 
        'model': model, 
        'historical_avg': round(historical_avg, 2),
        'historical_data': historical_data,
        'confidence': round(confidence, 1) if confidence is not None else None,
        'error': round(error, 2) if error is not None else None,
        'error_percent': round(error_percent, 1) if error_percent is not None else None,
        'difference': round(difference, 2) if difference is not None else None,
        'percentage_change': round(percentage_change, 1) if percentage_change is not None else None,
        'forecast_status': forecast_status,
    }

    return render(request, 'forecasting/forecast_detail.html', context)


@login_required
def model_comparison(request):
    """Compare performance across model versions. Restricted to Owner/Manager."""
    if not _check_forecasting_permission(request.user):
        return HttpResponseForbidden("Access denied.")

    company = request.user.company

    models_qs = ForecastModel.objects.filter(
        company=company, is_company_wide=True
    ).order_by('-version')

    models = []
    for model in models_qs:
        latest_run = model.runs.filter(status='COMPLETED').order_by('-completed_at').first()
        
        model_data = {
            'id': model.id, 'version': model.version, 'name': model.name, 'is_active': model.is_active,
            'trained_at': model.trained_at, 'validation_loss': model.validation_loss,
            'training_loss': model.training_loss, 'training_samples': model.training_samples,
            'epochs_trained': model.epochs_trained,
            'mae': latest_run.mae if latest_run else None,
            'rmse': latest_run.rmse if latest_run else None,
            'mape': latest_run.mape if latest_run else None,
        }
        models.append(model_data)

    return render(request, 'forecasting/model_comparison.html', {'models': models})


@login_required
@require_POST
def activate_model(request, model_id):
    """Switch active model to a specific version. Restricted to Owner/Manager."""
    if not _check_forecasting_permission(request.user):
        return JsonResponse({'success': False, 'error': 'Access denied.'}, status=403)

    company = request.user.company

    model = get_object_or_404(
        ForecastModel, id=model_id, company=company, is_company_wide=True
    )

    model.is_active = True
    model.save()

    return JsonResponse({'success': True, 'message': f'Model v{model.version} is now active.'})


@login_required
def forecast_list(request):
    """Paginated list of all forecast results. Restricted to Owner/Manager."""
    if not _check_forecasting_permission(request.user):
        return HttpResponseForbidden("Access denied.")

    company = request.user.company

    queryset = ForecastResult.objects.filter(
        company=company
    ).select_related('forecast_model').order_by('-forecast_date')

    search_query = request.GET.get('q', '').strip()
    if search_query:
        queryset = queryset.filter(
            Q(forecast_model__name__icontains=search_query) |
            Q(forecast_date__icontains=search_query)
        )

    model_filter = request.GET.get('model', '')
    if model_filter and model_filter != 'all':
        try:
            queryset = queryset.filter(forecast_model_id=int(model_filter))
        except (ValueError, TypeError):
            pass

    status_filter = request.GET.get('status', '')
    if status_filter == 'verified':
        queryset = queryset.filter(actual_quantity__isnull=False)
    elif status_filter == 'pending':
        queryset = queryset.filter(actual_quantity__isnull=True)

    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    if date_from:
        try:
            queryset = queryset.filter(forecast_date__gte=datetime.strptime(date_from, '%Y-%m-%d').date())
        except ValueError:
            pass
    if date_to:
        try:
            queryset = queryset.filter(forecast_date__lte=datetime.strptime(date_to, '%Y-%m-%d').date())
        except ValueError:
            pass

    paginator = Paginator(queryset, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    all_models = ForecastModel.objects.filter(
        company=company, is_company_wide=True
    ).order_by('-version')

    context = {
        'page_obj': page_obj, 'search_query': search_query, 'model_filter': model_filter,
        'status_filter': status_filter, 'date_from': date_from, 'date_to': date_to,
        'all_models': all_models, 'total_forecasts': queryset.count(),
    }

    return render(request, 'forecasting/forecast_list.html', context)


@login_required
def export_forecast(request, forecast_id):
    """Export a single forecast result as CSV. Restricted to Owner/Manager."""
    if not _check_forecasting_permission(request.user):
        return HttpResponseForbidden("Access denied.")

    company = request.user.company

    forecast = get_object_or_404(
        ForecastResult, id=forecast_id, company=company
    )

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="forecast_{forecast.forecast_date}.csv"'

    writer = csv.writer(response)
    writer.writerow(['Field', 'Value'])
    writer.writerow(['Forecast Date', forecast.forecast_date])
    writer.writerow(['Predicted Quantity', forecast.predicted_quantity])
    writer.writerow(['Lower Bound (95% CI)', forecast.lower_bound or 'N/A'])
    writer.writerow(['Upper Bound (95% CI)', forecast.upper_bound or 'N/A'])
    writer.writerow(['Actual Quantity', forecast.actual_quantity or 'N/A'])
    writer.writerow(['Model Used', forecast.forecast_model.name])
    writer.writerow(['Model Version', forecast.forecast_model.version])
    writer.writerow(['Forecast Horizon', f"{forecast.forecast_horizon} days"])
    writer.writerow(['Generated Date', forecast.created_at])
    
    writer.writerow([])
    writer.writerow(['BUSINESS METRICS', ''])
    writer.writerow(['Average Selling Price', f"₦{forecast.average_selling_price}" if forecast.average_selling_price else 'N/A'])
    writer.writerow(['Expected Revenue', f"₦{forecast.expected_revenue}" if forecast.expected_revenue else 'N/A'])
    writer.writerow(['Expected Profit', f"₦{forecast.expected_profit}" if forecast.expected_profit else 'N/A'])
    writer.writerow(['Historical Avg Revenue', f"₦{forecast.historical_avg_revenue}" if forecast.historical_avg_revenue else 'N/A'])

    return response


@login_required
@require_POST
def delete_forecast(request, forecast_id):
    """Delete a forecast result. Restricted to Owner/Manager."""
    if not _check_forecasting_permission(request.user):
        return JsonResponse({'success': False, 'error': 'Access denied.'}, status=403)

    company = request.user.company

    forecast = get_object_or_404(
        ForecastResult, id=forecast_id, company=company
    )

    forecast.delete()

    return JsonResponse({'success': True, 'message': 'Forecast deleted successfully.'})