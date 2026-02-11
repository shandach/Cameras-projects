import os

# Camera Settings
# NVR IP: 192.168.100.100 (from provided image)
# RTSP URL pattern varies by manufacturer (Hikvision, Dahua, etc.)
# Common pattern: rtsp://user:password@IP:554/Streaming/Channels/101 (Hikvision) or /cam/realmonitor?channel=1&subtype=0 (Dahua)

CAMERAS = [
    {
        "id": 1,
        "name": "Camera 01",
        "source": "rtsp://admin:a1234567@192.168.100.100:554/Streaming/Channels/101",
        "rois": [
            [(548, 446), (714, 536), (448, 816), (302, 718)],
            [(746, 564), (912, 686), (692, 1022), (498, 882)],
            [(1356, 504), (1422, 914), (1704, 700), (1518, 418)],
            [(1542, 392), (1728, 620), (1882, 438), (1676, 288)],
            [(1724, 250), (1896, 404), (1998, 260), (1818, 170)],
        ] 
    },
    {
        "id": 2,
        "name": "Camera 02",
        "source": "rtsp://admin:a1234567@192.168.100.100:554/Streaming/Channels/201",
        "rois": [
        ] 
    },
    {
        "id": 3,
        "name": "Camera 03",
        "source": "rtsp://admin:a1234567@192.168.100.100:554/Streaming/Channels/301",
        "rois": [
            [(1250, 760), (2457, 475), (2665, 1620), (1412, 1762)],
        ] 
    },
    {
        "id": 4,
        "name": "Camera 04",
        "source": "rtsp://admin:a1234567@192.168.100.100:554/Streaming/Channels/401",
        "rois": [
        ] 
    },
    {
        "id": 5,
        "name": "Camera 05",
        "source": "rtsp://admin:a1234567@192.168.100.100:554/Streaming/Channels/501",
        "rois": [
        ] 
    },
    {
        "id": 6,
        "name": "Camera 06",
        "source": "rtsp://admin:a1234567@192.168.100.100:554/Streaming/Channels/601",
        "rois": [
            [(642, 296), (888, 434), (548, 682), (390, 464)],
            [(1282, 690), (1750, 954), (1370, 1356), (926, 1090)],
        ] 
    },
    {
        "id": 7,
        "name": "Camera 07",
        "source": "rtsp://admin:a1234567@192.168.100.100:554/Streaming/Channels/701",
        "rois": [
            [(398, 261), (840, 120), (1099, 522), (584, 690)],
        ] 
    },
    {
        "id": 8,
        "name": "Camera 08",
        "source": "rtsp://admin:a1234567@192.168.100.100:554/Streaming/Channels/801",
        "rois": [
        ] 
    },
    {
        "id": 9,
        "name": "Camera 09",
        "source": "rtsp://admin:a1234567@192.168.100.100:554/Streaming/Channels/901",
        "rois": [
        ] 
    },
    {
        "id": 10,
        "name": "Camera 10",
        "source": "rtsp://admin:a1234567@192.168.100.100:554/Streaming/Channels/1001",
        "rois": [
            [(166, 489), (522, 705), (914, 314), (571, 123)],
        ] 
    },
    {
        "id": 11,
        "name": "Camera 11",
        "source": "rtsp://admin:a1234567@192.168.100.100:554/Streaming/Channels/1101",
        "rois": [
        ] 
    },
    {
        "id": 12,
        "name": "Camera 12",
        "source": "rtsp://admin:a1234567@192.168.100.100:554/Streaming/Channels/1201",
        "rois": [
        ] 
    },
    {
        "id": 13,
        "name": "Camera 13",
        "source": "rtsp://admin:a1234567@192.168.100.100:554/Streaming/Channels/1301",
        "rois": [
        ] 
    },
    {
        "id": 14,
        "name": "Camera 14",
        "source": "rtsp://admin:a1234567@192.168.100.100:554/Streaming/Channels/1401",
        "rois": [
        ] 
    },
    {
        "id": 15,
        "name": "Camera 15",
        "source": "rtsp://admin:a1234567@192.168.100.100:554/Streaming/Channels/1501",
        "rois": [
        ] 
    },
    {
        "id": 16,
        "name": "Camera 16",
        "source": "rtsp://admin:a1234567@192.168.100.100:554/Streaming/Channels/1601",
        "rois": [
        ] 
    },
]

# Owners/Employees Mapping
# Map Workplace ID -> Name
# IDs are assigned sequentially based on ACTIVE cameras (with ROIs).
# Cam 1 (5 ROIs): IDs 1-5
# Cam 3 (1 ROI): ID 6
# Cam 6 (2 ROIs): IDs 7-8
# Cam 7 (1 ROI): ID 9
# Cam 10 (1 ROI): ID 10
WORKPLACE_OWNERS = {
    # Camera 1 (IDs 1-5)
    1: 'Operator 6',
    2: 'Operator 7',
    3: 'Operator 8',
    4: 'Operator 9',
    5: 'Operator 10',
    
    # Camera 3 (ID 6)
    6: 'Operator 3',
    
    # Camera 6 (IDs 7-8)
    7: 'Operator 11',
    8: 'Operator 13',
    
    # Camera 7 (ID 9)
    9: 'Operator 2',
    
    # Camera 10 (ID 10)
    10: 'Operator 1'
}

# Logging Config
LOG_DIR = 'logs'
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

RAW_LOG_FILE = os.path.join(LOG_DIR, 'raw_logs.csv')
SESSION_LOG_FILE = os.path.join(LOG_DIR, 'sessions.csv')


# Detection Constants

# Logic Constants
T_ENTER = 2.0      # Seconds to trigger 'occupied' (User Requested 2s)
T_EXIT  = 10.0     # Seconds to trigger 'empty' after sticky signal lost (Optimized: 10s)
T_ID_MEMORY = 5.0  # Seconds to keep "Person Detected" status if model blinks (Blindness protection)

# Resolution for Processing (Shared Memory)
# We resize to this BEFORE storing in RAM to save bandwidth
# User Directive: Start with 960x540 (qHD). If still bad -> 720p.
SHM_WIDTH = 960
SHM_HEIGHT = 540
SHM_CHANNELS = 3
SHM_SIZE = SHM_WIDTH * SHM_HEIGHT * SHM_CHANNELS

# Source Resolution (Estimated from ROIs as 4K)
# Used to scale ROIs down to SHM size
SOURCE_WIDTH = 3840
SOURCE_HEIGHT = 2160


# Database Configuration
DB_DSN = "postgresql://postgres:bqLIttocGdNiKQRwYaRItoZIzTfGdjfA@switchback.proxy.rlwy.net:30759/railway"
DB_TABLE = "events" # Production Table
BRANCH_ID = 11673
BRANCH_NAME = "Qatortol BXM"
