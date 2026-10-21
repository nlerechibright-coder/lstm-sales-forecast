from apps.core.utils import get_file_headers

# Place a dummy 'test.csv' or 'test.xlsx' in your root directory to test
test_file = 'test.csv' 
headers = get_file_headers(test_file)

if headers:
    print(f"Successfully extracted headers: {headers}")
else:
    print("Failed to extract headers. Check file path or format.")