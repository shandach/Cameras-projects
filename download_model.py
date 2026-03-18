"""
Download YOLOv10s model and optionally export to OpenVINO.

Usage:
    python download_model.py
    python download_model.py --skip-openvino
"""
import requests
import os
import sys
import argparse
from pathlib import Path

# YOLOv10s from ultralytics releases
MODEL_URL = "https://github.com/THU-MIG/yolov10/releases/download/v1.1/yolov10s.pt"
MODEL_FILENAME = "yolov10s.pt"


def download_model():
    """Download YOLOv10s model"""
    if os.path.exists(MODEL_FILENAME):
        size_mb = os.path.getsize(MODEL_FILENAME) / (1024 * 1024)
        print(f"✅ {MODEL_FILENAME} already exists ({size_mb:.1f} MB)")
        return True
    
    print(f"⬇️  Downloading {MODEL_FILENAME}...")
    print(f"   URL: {MODEL_URL}")
    
    try:
        response = requests.get(MODEL_URL, allow_redirects=True, stream=True)
        response.raise_for_status()
        
        total_size = int(response.headers.get('content-length', 0))
        downloaded = 0
        
        with open(MODEL_FILENAME, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
                downloaded += len(chunk)
                if total_size > 0:
                    pct = downloaded / total_size * 100
                    print(f"\r   Progress: {pct:.1f}% ({downloaded / 1024 / 1024:.1f} MB)", end="", flush=True)
        
        print()  # newline after progress
        size_mb = os.path.getsize(MODEL_FILENAME) / (1024 * 1024)
        print(f"✅ Downloaded {MODEL_FILENAME} ({size_mb:.1f} MB)")
        return True
        
    except Exception as e:
        print(f"❌ Download failed: {e}")
        # Fallback: try using ultralytics auto-download
        print(f"🔄 Trying ultralytics auto-download...")
        try:
            from ultralytics import YOLO
            model = YOLO("yolov10s.pt")
            print(f"✅ Model downloaded via ultralytics")
            return True
        except Exception as e2:
            print(f"❌ Fallback also failed: {e2}")
            return False


def export_openvino():
    """Export to OpenVINO after download"""
    try:
        # Check if openvino is installed
        import openvino
        print(f"\n🔄 OpenVINO {openvino.__version__} detected. Exporting...")
        
        # Use the export script
        sys.path.insert(0, str(Path(__file__).parent))
        from scripts.export_openvino import export_to_openvino
        from config import YOLO_IMGSZ
        
        export_to_openvino(
            model_path=MODEL_FILENAME,
            imgsz=YOLO_IMGSZ,
            half=True
        )
    except ImportError:
        print(f"\n💡 OpenVINO not installed. To optimize for Intel CPUs:")
        print(f"   pip install openvino>=2024.0.0")
        print(f"   python scripts/export_openvino.py")


def main():
    parser = argparse.ArgumentParser(description="Download YOLOv10s model")
    parser.add_argument("--skip-openvino", action="store_true",
                        help="Skip OpenVINO export after download")
    args = parser.parse_args()
    
    success = download_model()
    
    if success and not args.skip_openvino:
        export_openvino()
    elif not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
