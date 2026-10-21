import pandas as pd
import os

def get_file_headers(file_path):
    """
    Detects file extension and extracts column headers.
    Returns a list of strings representing the headers.
    """
    ext = os.path.splitext(file_path)[1].lower()
    
    try:
        if ext == '.csv':
            # Read only the first row to get headers
            df = pd.read_csv(file_path, nrows=0)
        elif ext in ['.xlsx', '.xls']:
            df = pd.read_excel(file_path, nrows=0)
        else:
            return None
        
        return list(df.columns)
    except Exception as e:
        print(f"Error reading headers: {e}")
        return None