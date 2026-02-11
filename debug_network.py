import os
import cv2
import sys
import socket
import subprocess
from dotenv import load_dotenv

load_dotenv()

def check_ping(host):
    """Diagnose connectivity"""
    print(f"\n📡 PING CHECK: {host}")
    # Windows uses -n, Linux/Mac uses -c
    param = '-n' if sys.platform.lower() == 'win32' else '-c'
    command = ['ping', param, '1', host]
    
    try:
        startupinfo = None
        if sys.platform.lower() == 'win32':
            # Hide console window on Windows
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            
        result = subprocess.call(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, startupinfo=startupinfo)
        return result == 0
    except Exception as e:
        print(f"⚠️ Ping error: {e}")
        return False

def check_port(host, port):
    """Diagnose port open"""
    print(f"\n🔌 PORT CHECK: {host}:{port}")
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(2)
    result = sock.connect_ex((host, port))
    sock.close()
    return result == 0

def check_stream(url):
    """Diagnose OpenCV stream"""
    print(f"\n🎥 STREAM CHECK:")
    # Mask password for display
    display_url = url
    if '@' in url:
        parts = url.split('@')
        display_url = f"{parts[0].split(':')[0]}:***@{parts[1]}"
    print(f"   URL: {display_url}")
    
    # Try opening with TCP
    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"
    cap = cv2.VideoCapture(url)
    
    if not cap.isOpened():
        print("❌ FAILED: precise reason unknown (OpenCV generic error)")
        return False
    
    ret, frame = cap.read()
    if ret:
        print(f"✅ SUCCESS: Received frame {frame.shape}")
        # Save a debug image
        cv2.imwrite("debug_frame.jpg", frame)
        print("   Saved debug_frame.jpg")
    else:
        print("⚠️ CONNECTED BUT NO FRAME (Stream timeout?)")
        
    cap.release()
    return ret

if __name__ == "__main__":
    print(f"Python: {sys.version.split()[0]}")
    print(f"OpenCV: {cv2.__version__}")
    
    # 1. Get Camera 1 Config
    cam1_url = os.environ.get("CAMERA_1_URL")
    if not cam1_url:
        print("\n❌ CRITICAL: CAMERA_1_URL not found in environment!")
        print("   Did you create existing .env file on this PC?")
        sys.exit(1)
        
    # Inject creds
    user = os.environ.get("RTSP_USER")
    pwd = os.environ.get("RTSP_PASSWORD")
    if user and pwd and 'rtsp://' in cam1_url:
        cam1_url = cam1_url.replace('rtsp://', f'rtsp://{user}:{pwd}@')
        
    # Extract Host/Port
    try:
        # rtsp://user:pass@192.168.100.100:554/...
        # Split by @, take right part -> IP:Port/Path
        auth_split = cam1_url.split('@')
        if len(auth_split) > 1:
            host_part = auth_split[1]
        else:
            host_part = cam1_url.replace('rtsp://', '')
            
        host = host_part.split(':')[0]
        port = 554 # Default RTSP
        if ':' in host_part:
            port_str = host_part.split(':')[1].split('/')[0]
            if port_str.isdigit():
                port = int(port_str)
    except:
        host = "Unknown"
        port = 554

    # 2. Run Diagnostics
    if host != "Unknown":
        if check_ping(host):
            print("✅ PING: Success")
            if check_port(host, port):
                print("✅ PORT: Open")
                check_stream(cam1_url)
            else:
                print(f"❌ PORT: Closed (Firewall blocking {port}?)")
        else:
            print(f"❌ PING: Host Unreachable ({host})")
            print("   Check network cable / VPN.")
    else:
        print("⚠️ Could not parse host IP")
        check_stream(cam1_url)
