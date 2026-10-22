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
from django.contrib.auth.hashers import make_password

def run():
    username = 'chinedu'
    email = 'chinedu@lstm.com'
    password = 'chinedu12345' # Change this to your preferred password
    hashed_password = make_password(password)
    
    print("🔍 Checking database for existing user...")
    
    with connection.cursor() as cursor:
        # 1. Check if user already exists
        cursor.execute("SELECT username FROM accounts_customuser WHERE username = %s", [username])
        if cursor.fetchone():
            print(f"⚠️ User '{username}' already exists in the database! You can log in now.")
            return
            
        print("👤 Creating superuser via raw SQL...")
        
        try:
            # 2. Insert the user directly, including date_joined and last_login to satisfy NOT NULL constraints
            cursor.execute("""
                INSERT INTO accounts_customuser 
                (username, email, password, is_staff, is_superuser, is_active, first_name, last_name, full_name, phone, user_type, discipline, date_joined, last_login)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """, [
                username, 
                email, 
                hashed_password, 
                True,           # is_staff
                True,           # is_superuser
                True,           # is_active
                'System',       # first_name
                'Admin',        # last_name
                'System Admin', # full_name
                '08000000000',  # phone
                'SYSTEM_ADMIN', # user_type
                None            # discipline
            ])
            
            print(f"✅ Successfully created superuser: {username}")
            print(f"👉 Password: {password}")
            print("🚀 You can now log in at https://lstm-sales-forecast-2.onrender.com/admin/")
            
        except Exception as e:
            print(f"❌ Error creating user: {e}")

if __name__ == '__main__':
    run()