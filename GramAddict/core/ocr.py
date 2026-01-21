"""OCR utility module for text extraction from screenshots.

Provides fallback OCR-based text detection when UiAutomator2 fails to
read text from UI elements (common issue with Instagram profile counters).
"""
import platform
import re
from typing import Optional, Dict
import logging

logger = logging.getLogger(__name__)


def _ensure_tesseract_cmd(pytesseract):
    """Configure Tesseract binary path for Windows if needed."""
    if platform.system() == "Windows":
        # Default Windows installation path
        pytesseract.pytesseract.tesseract_cmd = (
            r"C:\Program Files\Tesseract-OCR\tesseract.exe"
        )


def ocr_text_in_bounds(device, bounds: Dict[str, int]) -> Optional[str]:
    """Extract text from a screen region using OCR.
    
    Args:
        device: DeviceFacade instance
        bounds: Dictionary with 'left', 'top', 'right', 'bottom' coordinates
        
    Returns:
        Extracted text string or None if OCR failed
    """
    try:
        import pytesseract
    except ImportError:
        logger.debug(
            "pytesseract not installed. Install with: pip install pytesseract"
        )
        return None

    try:
        _ensure_tesseract_cmd(pytesseract)

        # Take screenshot and crop to target region
        img = device.screenshot()
        crop = img.crop(
            (bounds["left"], bounds["top"], bounds["right"], bounds["bottom"])
        )

        # PSM 7 = single line, whitelist = digits and common counter chars
        config = "--psm 7 -c tessedit_char_whitelist=0123456789KMkm.,"
        text = pytesseract.image_to_string(crop, config=config) or ""
        text = text.strip().replace(" ", "")
        
        logger.debug(f"OCR extracted text: '{text}' from bounds {bounds}")
        return text or None
        
    except pytesseract.TesseractNotFoundError:
        logger.error(
            "Tesseract OCR engine not found. Install it:\n"
            "  - Linux: sudo apt install tesseract-ocr\n"
            "  - macOS: brew install tesseract\n"
            "  - Windows: Download from https://github.com/UB-Mannheim/tesseract/wiki"
        )
        return None
    except Exception as e:
        logger.debug(f"OCR failed: {str(e)}")
        return None


def ocr_counter_text_near(device, bounds: Dict[str, int]) -> Optional[str]:
    """Extract counter text with slight padding around the bounds.
    
    Adds small padding to handle cases where the bounding box is too tight.
    
    Args:
        device: DeviceFacade instance
        bounds: Dictionary with 'left', 'top', 'right', 'bottom' coordinates
        
    Returns:
        Extracted text string or None if OCR failed
    """
    w = device.get_info()["displayWidth"]
    h = device.get_info()["displayHeight"]

    # Add 2% horizontal and 1% vertical padding
    pad_x = int(0.02 * w)
    pad_y = int(0.01 * h)

    padded_bounds = {
        "left": max(0, bounds["left"] - pad_x),
        "top": max(0, bounds["top"] - pad_y),
        "right": min(w, bounds["right"] + pad_x),
        "bottom": min(h, bounds["bottom"] + pad_y),
    }
    
    return ocr_text_in_bounds(device, padded_bounds)


def normalize_counter_text(s: str) -> str:
    """Normalize counter text by removing commas and spaces.
    
    Examples:
        '24.4K' -> '24.4K'
        '2,197' -> '2197'
        '1 234' -> '1234'
    """
    if not s:
        return ""
    s = s.strip()
    s = s.replace(",", "")
    s = s.replace(" ", "")
    return s


def parse_counter_with_suffix(s: str) -> Optional[int]:
    """Parse Instagram-style counter text to integer.
    
    Handles formats like:
        - '2197' -> 2197
        - '24.4K' -> 24400
        - '1.2M' -> 1200000
        - '2,197' -> 2197
        
    Args:
        s: Counter text string
        
    Returns:
        Integer value or None if parsing failed
    """
    if not s:
        return None
    
    s = normalize_counter_text(s).upper()

    # Match number with optional K or M suffix
    m = re.match(r"^(\d+(?:\.\d+)?)([KM])?$", s)
    if not m:
        logger.debug(f"Failed to parse counter text: '{s}'")
        return None

    val = float(m.group(1))
    suffix = m.group(2)
    
    if suffix == "K":
        val *= 1000
    elif suffix == "M":
        val *= 1000000
        
    return int(val)
