"""
Utility functions for Workplace Monitoring
"""
from typing import Tuple

def is_point_in_box(point: Tuple[int, int], bbox: Tuple[int, int, int, int]) -> bool:
    """
    Check if a point (x, y) is inside a bounding box (x1, y1, x2, y2).
    
    Args:
        point: (x, y)
        bbox: (x1, y1, x2, y2)
        
    Returns:
        True if point is inside bbox, else False
    """
    x, y = point
    x1, y1, x2, y2 = bbox
    
    return x1 <= x <= x2 and y1 <= y <= y2
