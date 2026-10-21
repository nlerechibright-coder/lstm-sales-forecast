import os
import django

# 1. Set the environment variables for the production database
os.environ['DB_NAME'] = 'cewms'
os.environ['DB_USER'] = 'cewmsuser'
os.environ['DB_PASSWORD'] = 'Wc1KVQIsEmbYZKiujAmTGZXJlVzmUG3r'
os.environ['DB_HOST'] = 'dpg-dba9a22jnfac73erogh0-a.frankfurt-postgres.render.com'
os.environ['DB_PORT'] = '5432'
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

django.setup()

from django.db import connection

print("🔄 Connecting to database to reset...")
try:
    with connection.cursor() as cursor:
        # This completely wipes all tables and migration history
        cursor.execute("DROP SCHEMA public CASCADE;")
        cursor.execute("CREATE SCHEMA public;")
        # Grant permissions back to your user
        cursor.execute("GRANT ALL ON SCHEMA public TO cewmsuser;")
        cursor.execute("GRANT ALL ON SCHEMA public TO public;")
    print("✅ Database successfully wiped and reset!")
    print("🚀 You can now run 'python manage.py migrate'")
except Exception as e:
    print(f"❌ Error: {e}")