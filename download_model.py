import requests
import os

url = "https://github.com/ultralytics/assets/releases/download/v8.2.0/yolov8s.pt"
filename = "yolov8s.pt"

print(f"Downloading {filename} from {url}...")

try:
    # Use allow_redirects=True for -L equivalent
    response = requests.get(url, allow_redirects=True, stream=True)
    response.raise_for_status()
    
    with open(filename, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
            
    print(f"✅ Successfully downloaded {filename}")
    size_mb = os.path.getsize(filename) / (1024 * 1024)
    print(f"File size: {size_mb:.2f} MB")
    
except Exception as e:
    print(f"❌ Error: {e}")
    exit(1)
