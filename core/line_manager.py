"""
Manages counting lines for multiple cameras.
Loads from and saves to JSON.
"""
import json
import os
from pathlib import Path
from typing import Dict, Optional, Tuple

DB_PATH = Path('database')
DB_PATH.mkdir(exist_ok=True)
LINES_FILE = DB_PATH / "lines.json"

class LineManager:
    """Manages crossing lines configuration across all cameras"""
    
    def __init__(self):
        self.lines: Dict[int, dict] = {}  # camera_db_id -> config dict
        self._load_from_json()
        
    def _load_from_json(self):
        """Load lines from JSON file"""
        if LINES_FILE.exists():
            try:
                with open(LINES_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # Convert str keys back to int camera_ids
                    self.lines = {int(k): v for k, v in data.items()}
            except Exception as e:
                print(f"[LineManager] Failed to load lines: {e}")
                self.lines = {}
    
    def _save_to_json(self):
        """Save lines to JSON"""
        try:
            with open(LINES_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.lines, f, indent=4)
        except Exception as e:
            print(f"[LineManager] Failed to save lines: {e}")
            
    def get_line(self, camera_id: int) -> Optional[dict]:
        """Get line configuration for specific camera"""
        return self.lines.get(camera_id)
        
    def set_line(self, camera_id: int, start: Tuple[int, int], end: Tuple[int, int], direction: str = 'down'):
        """Create or update a line for a camera"""
        self.lines[camera_id] = {
            "start": start,
            "end": end,
            "direction": direction
        }
        self._save_to_json()
        
    def delete_line(self, camera_id: int):
        """Delete line for a camera"""
        if camera_id in self.lines:
            del self.lines[camera_id]
            self._save_to_json()

# Global line instance
line_manager = LineManager()
