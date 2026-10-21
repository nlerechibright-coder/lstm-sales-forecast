from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_POST
from .models import UploadJob
from .utils import get_file_headers
from sales.services.mapping_service import suggest_mappings, apply_mappings_bulk
from sales.services.normalization_service import normalize_dataframe, get_normalization_summary
from sales.services.import_service import import_valid_rows
from forecasting.tasks import trigger_retraining_check
from forecasting.services.task_runner import run_task
import pandas as pd
import os


@login_required
def upload_sales_data(request):
    recent_jobs = UploadJob.objects.filter(
        company=request.user.company,
        user=request.user
    ).order_by('-created_at')[:8]

    if request.method == 'POST':
        if not request.FILES.get('sales_file'):
            return render(request, 'core/upload.html', {
                'error': 'Please choose a CSV or Excel file before uploading.',
                'recent_jobs': recent_jobs,
            })

        uploaded_file = request.FILES['sales_file']
        file_ext = os.path.splitext(uploaded_file.name)[1].lower()

        if file_ext not in ['.csv', '.xlsx', '.xls']:
            return render(request, 'core/upload.html', {
                'error': 'Unsupported file format. Upload a CSV, XLSX, or XLS file.',
                'recent_jobs': recent_jobs,
            })

        job = UploadJob.objects.create(
            company=request.user.company,
            user=request.user,
            file=uploaded_file,
            file_type=file_ext.replace('.', '')
        )

        headers = get_file_headers(job.file.path)

        if headers:
            job.status = 'HEADERS_READ'
            job.save()
            return redirect('mapping_interface', job_id=job.id)

        job.status = 'FAILED'
        job.error_message = "Could not extract headers."
        job.save()
        return render(request, 'core/upload.html', {
            'error': 'File processing failed. Confirm the file has a header row and try again.',
            'recent_jobs': recent_jobs,
        })

    return render(request, 'core/upload.html', {'recent_jobs': recent_jobs})


@login_required
def download_sales_template(request):
    """Download a simple sales history import template."""
    content = (
        "date,product_name,sku,sales_quantity,sales_amount,discount\r\n"
        "2026-07-01,Sample Product,SKU-001,10,25000.00,0.00\r\n"
    )
    response = HttpResponse(content, content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="sales_history_template.csv"'
    return response


@login_required
def mapping_interface(request, job_id):
    job = get_object_or_404(UploadJob, id=job_id, company=request.user.company)

    if job.status not in ['HEADERS_READ', 'MAPPED']:
        return redirect('upload_sales')

    headers = get_file_headers(job.file.path)
    suggestions = suggest_mappings(headers, request.user.company.id)

    confirmed_mappings = job.mapped_columns or {}

    context = {
        'job': job,
        'headers': headers,
        'suggestions': suggestions,
        'confirmed_mappings': confirmed_mappings,
        'known_fields': [
            ('date', 'Date'),
            ('product_name', 'Product Name'),
            ('sku', 'SKU / Product Code'),
            ('sales_quantity', 'Sales Quantity'),
            ('sales_amount', 'Sales Amount'),
            ('discount', 'Discount'),
        ]
    }
    return render(request, 'core/mapping.html', context)


@login_required
@require_POST
def confirm_mapping(request):
    job_id = request.POST.get('job_id')
    job = get_object_or_404(UploadJob, id=job_id, company=request.user.company)

    mapped_columns = {}
    for header in request.POST.getlist('headers[]'):
        field = request.POST.get(f'map_{header}')
        if field:
            mapped_columns[header] = field

    required = {'date', 'sales_quantity'}
    mapped_fields = set(mapped_columns.values())
    missing = required - mapped_fields

    if missing:
        return JsonResponse({
            'success': False,
            'error': f"Missing required fields: {', '.join(missing)}"
        })

    job.mapped_columns = mapped_columns
    job.status = 'MAPPED'
    job.save()

    apply_mappings_bulk(request.user.company.id, mapped_columns)

    return JsonResponse({
        'success': True,
        'redirect_url': reverse('execute_import', kwargs={'job_id': job.id})
    })


@login_required
def execute_import(request, job_id):
    job = get_object_or_404(UploadJob, id=job_id, company=request.user.company)

    if job.status != 'MAPPED' or not job.mapped_columns:
        return redirect('mapping_interface', job_id=job.id)

    file_path = job.file.path
    ext = os.path.splitext(file_path)[1].lower()

    if ext == '.csv':
        df = pd.read_csv(file_path)
    else:
        df = pd.read_excel(file_path)

    valid_rows, invalid_rows = normalize_dataframe(
        df, job.mapped_columns, job.id
    )

    import_result = import_valid_rows(valid_rows, job.company_id, job.id)

    if import_result['imported'] > 0:
        job.status = 'IMPORTED'
        try:
            run_task(trigger_retraining_check, job.company_id)
        except Exception:
            pass
    else:
        job.status = 'FAILED'
        job.error_message = "No valid rows could be imported."
    job.save()

    norm_summary = get_normalization_summary(job.id)

    context = {
        'job': job,
        'imported': import_result['imported'],
        'skipped': import_result['skipped'],
        'errors': import_result['errors'],
        'invalid_rows': invalid_rows,
        'norm_summary': norm_summary,
    }
    return render(request, 'core/import_result.html', context)