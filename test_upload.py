import requests
import os

url = "http://127.0.0.1:5000/"
filename = "reptask_P1JRNC_DATABRICKS_1_B (5).log"

if not os.path.exists(filename):
    print(f"File not found: {filename}")
    exit(1)

print(f"Uploading {filename}...")
try:
    with open(filename, 'rb') as f:
        files = {'log_file': (filename, f)}
        response = requests.post(url, files=files)
    
    print(f"Status Code: {response.status_code}")
    if response.status_code == 200:
        # Check if "Performance samples" is in the response text
        if "Performance samples" in response.text:
            print("Success: Performance samples found in response.")
        elif "No [PERFORMANCE] lines detected" in response.text:
            print("Warning: No performance lines detected.")
        else:
            print("Unknown state. Snippet of response:")
            print(response.text[:500])
    else:
        print(f"Error: {response.text[:500]}")

except Exception as e:
    print(f"Exception: {e}")

