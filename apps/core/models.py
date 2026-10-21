from django.db import models
from django.conf import settings
from accounts.models import Company


class UploadJob(models.Model):
    STATUS_CHOICES = [
        ('UPLOADED', 'Uploaded'),
        ('HEADERS_READ', 'Headers Read'),
        ('MAPPED', 'Mapped'),
        ('IMPORTED', 'Imported'),
        ('FAILED', 'Failed'),
    ]

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name='upload_jobs'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='upload_jobs'
    )
    file = models.FileField(upload_to='uploads/sales/%Y/%m/%d/')
    file_type = models.CharField(max_length=10)  # 'csv' or 'xlsx'
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='UPLOADED')
    mapped_columns = models.JSONField(
        blank=True,
        null=True,
        help_text="JSON mapping of uploaded headers to database field names. "
                  "Example: {'Sales Qty': 'sales_quantity', 'Date': 'date'}"
    )
    error_message = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'core_upload_jobs'
        ordering = ['-created_at']

    def __str__(self):
        return f"Job {self.id} - {self.company.name} - {self.status}"