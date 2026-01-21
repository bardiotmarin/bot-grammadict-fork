import platform
import re
from typing import Optional, Dict
import logging

logger = logging.getLogger(__name__)

def _ensure_tesseract_cmd(pytesseract):
    if platform.system() == "Windows":
        # Default typical path, user might need to adjust this or add to PATH
        pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

def ocr_text_in_bounds(device, bounds: Dict[str, int]) -> Optional[str]:
    """
    Perform OCR on a specific region of the screen defined by bounds.
    bounds: dict with keys "left", "top", "right", "bottom"
    """
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        logger.error("pytesseract or Pillow not installed. Cannot perform OCR.")
        return None

    try:
        _ensure_tesseract_cmd(pytesseract)

        # device.screenshot() usually returns a PIL Image or saves to file
        # If it saves to file, we need to open it. Assuming device_facade.screenshot() returns PIL Image based on existing code
        img = device.screenshot() 
        
        # Crop the image to the specified bounds
        crop = img.crop((bounds["left"], bounds["top"], bounds["right"], bounds["bottom"]))

        # Configure tesseract for single line of text, assuming numbers and K/M suffixes
        # psm 7: Treat the image as a single text line.
        config = "--psm 7" 
        
        text = pytesseract.image_to_string(crop, config=config) or ""
        text = text.strip()
        return text or None
    except Exception as e:
        logger.error(f"OCR failed: {e}")
        return None

def ocr_counter_text_near(device, bounds: Dict[str, int]) -> Optional[str]:
    """
    Performs OCR with slightly padded bounds to ensure the text is fully captured.
    Useful if the UI element bounds are too tight.
    """
    info = device.get_info()
    w = info["displayWidth"]
    h = info["displayHeight"]

    # Add small padding (e.g. 1% of screen size)
    pad_x = int(0.01 * w)
    pad_y = int(0.005 * h)

    b = {
        "left": max(0, bounds["left"] - pad_x),
        "top": max(0, bounds["top"] - pad_y),
        "right": min(w, bounds["right"] + pad_x),
        "bottom": min(h, bounds["bottom"] + pad_y),
    }
    return ocr_text_in_bounds(device, b)

def parse_counter_with_suffix(s: str) -> Optional[int]:
    """
    Parses strings like '24.4K', '1.2M', '2,197', '2.197' into integers.
    """
    if not s:
        return None
    
    # Remove common noise and normalize
    s = s.strip().upper()
    s = s.replace(",", "").replace(" ", "")
    
    # Handle cases where OCR might read 'O' as '0' or similar if needed, 
    # but strictly we look for number + suffix
    
    # Regex to capture number part and optional suffix (K or M)
    # Accepts 24.4K, 24K, 100, etc.
    m = re.match(r"^(\d+(?:\.\d+)?)([KM])?$", s)
    if not m:
        # Try looser matching if exact match fails (e.g. noise chars)
        m = re.search(r"(\d+(?:\.\d+)?)([KM])?", s)
        if not m:
            return None

    try:
        val = float(m.group(1))
        suf = m.group(2)
        
        if suf == "K":
            val *= 1_000
        elif suf == "M":
            val *= 1_000_000
            
        return int(val)
    except ValueError:
        return None
