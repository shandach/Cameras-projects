"""
Export YOLOv10s model to OpenVINO IR format (FP16).

Usage:
    python scripts/export_openvino.py
    python scripts/export_openvino.py --model yolov10s.pt --imgsz 960

This creates a directory like 'yolov10s_openvino_model/' next to the .pt file.
The main detector.py will auto-detect and use this directory on startup.
"""
import argparse
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def export_to_openvino(model_path: str, imgsz: int = 960, half: bool = True):
    """
    Export YOLO model to OpenVINO format.
    
    Args:
        model_path: Path to .pt model file
        imgsz: Input image size (default 960)
        half: Use FP16 quantization (default True for better speed)
    """
    from ultralytics import YOLO
    
    pt_path = Path(model_path)
    if not pt_path.exists():
        print(f"❌ Model file not found: {model_path}")
        print(f"   Run 'python download_model.py' first to download the model.")
        sys.exit(1)
    
    print("=" * 50)
    print(f"  OpenVINO Export")
    print("=" * 50)
    print(f"  Model:    {model_path}")
    print(f"  Format:   OpenVINO IR ({'FP16' if half else 'FP32'})")
    print(f"  ImgSize:  {imgsz}x{imgsz}")
    print("=" * 50)
    
    # Load model
    print(f"\n📦 Loading model: {model_path}")
    model = YOLO(model_path)
    
    # Export to OpenVINO
    print(f"🔄 Exporting to OpenVINO (this may take 1-3 minutes)...")
    export_path = model.export(
        format="openvino",
        half=half,
        imgsz=imgsz
    )
    
    print(f"\n✅ Export complete!")
    print(f"   OpenVINO model saved to: {export_path}")
    
    # Verify the exported model
    openvino_dir = Path(export_path)
    xml_files = list(openvino_dir.glob("*.xml"))
    bin_files = list(openvino_dir.glob("*.bin"))
    
    if xml_files and bin_files:
        xml_size = xml_files[0].stat().st_size / (1024 * 1024)
        bin_size = bin_files[0].stat().st_size / (1024 * 1024)
        print(f"   XML: {xml_files[0].name} ({xml_size:.1f} MB)")
        print(f"   BIN: {bin_files[0].name} ({bin_size:.1f} MB)")
    
    # Quick validation: load and run dummy inference
    print(f"\n🧪 Validating exported model...")
    try:
        import numpy as np
        test_model = YOLO(str(openvino_dir))
        dummy_frame = np.zeros((imgsz, imgsz, 3), dtype=np.uint8)
        results = test_model(dummy_frame, verbose=False)
        print(f"✅ Validation passed! Model loads and runs correctly.")
    except Exception as e:
        print(f"⚠️ Validation warning: {e}")
        print(f"   The model was exported but may need investigation.")
    
    print(f"\n📋 Next steps:")
    print(f"   1. The detector will auto-detect this model on next startup")
    print(f"   2. Set YOLO_USE_OPENVINO=true in .env (already default)")
    print(f"   3. Run 'python main.py' to verify")


def main():
    parser = argparse.ArgumentParser(description="Export YOLO model to OpenVINO format")
    parser.add_argument("--model", type=str, default=None,
                        help="Path to .pt model (default: from config)")
    parser.add_argument("--imgsz", type=int, default=None,
                        help="Input image size (default: from config)")
    parser.add_argument("--fp32", action="store_true",
                        help="Use FP32 instead of FP16 (slower but more accurate)")
    
    args = parser.parse_args()
    
    # Load defaults from config if not specified
    if args.model is None or args.imgsz is None:
        from config import YOLO_MODEL, YOLO_IMGSZ
        model_path = args.model or YOLO_MODEL
        imgsz = args.imgsz or YOLO_IMGSZ
    else:
        model_path = args.model
        imgsz = args.imgsz
    
    export_to_openvino(
        model_path=model_path,
        imgsz=imgsz,
        half=not args.fp32
    )


if __name__ == "__main__":
    main()
