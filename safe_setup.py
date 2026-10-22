import os
import sys
import django

# 1. Setup paths and Django environment
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.db import connection
from django.contrib.auth import get_user_model

User = get_user_model()

def run():
    print("🔍 Checking database tables...")
    with connection.cursor() as cursor:
        # Get all tables in the public schema
        cursor.execute("""
            SELECT table_name FROM information_schema.tables 
            WHERE table_schema = 'public';
        """)
        tables = [row[0] for row in cursor.fetchall()]
        
        # Check for the user table (singular or plural)
        user_tables = [t for t in tables if 'customuser' in t.lower() or 'user' in t.lower()]
        print(f"✅ Found user-related tables: {user_tables}")

    print("\n👤 Attempting to create Superuser...")
    username = 'chinedu'
    email = 'chinedu@lstm.com'
    password = 'chinedu12345' # Change this to your preferred password

    if User.objects.filter(username=username).exists():
        print(f"⚠️ User '{username}' already exists! You can log in with this account.")
    else:
        try:
            # Create the superuser safely
            user = User.objects.create_superuser(
                username=username,
                email=email,
                password=password
            )
            print(f"✅ Successfully created superuser: {username}")
            print(f"👉 Password: {password}")
        except Exception as e:
            print(f"❌ Error creating user: {e}")
            print("💡 Tip: If it says 'role' or 'company' is required, your CustomUser model needs those fields. Let me know the exact error!")

if __name__ == '__main__':
    run()