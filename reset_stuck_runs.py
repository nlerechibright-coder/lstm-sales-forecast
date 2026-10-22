import os
import sys
import django

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from forecasting.models import ForecastRun

def run():
    # Find all runs stuck in 'RUNNING' or 'PENDING'
    stuck_runs = ForecastRun.objects.filter(status__in=['RUNNING', 'PENDING'])
    count = stuck_runs.count()
    
    if count > 0:
        # Reset them to FAILED
        stuck_runs.update(status='FAILED', error_message='Manually cancelled due to timeout')
        print(f"✅ Successfully cancelled {count} stuck training runs!")
    else:
        print("ℹ️ No stuck runs found. Your queue is clean.")

if __name__ == '__main__':
    run()