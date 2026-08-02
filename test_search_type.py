"""
Test script to type into the Instagram search bar.
Assumes the search page is already open on the emulator.
"""
import uiautomator2 as u2
import time
import subprocess

DEVICE = "127.0.0.1:21523"
APP_ID = "com.instagram.android"
SEARCH_TEXT = "deephouse"

d = u2.connect(DEVICE)

print("=== Step 1: Dump current UI ===")
hierarchy = d.dump_hierarchy()

# Find search edit text
search_id = f"{APP_ID}:id/action_bar_search_edit_text"
search_box = d(resourceId=search_id)

if search_box.exists:
    print(f"[OK] Search EditText found!")
    info = search_box.info
    print(f"  Focused: {info.get('focused')}")
    print(f"  Text: {info.get('text')}")
    print(f"  Enabled: {info.get('enabled')}")
    print(f"  Bounds: {info.get('bounds')}")
else:
    print("✗ Search EditText NOT found by resource ID")
    # Try fallback search
    for cls in ["android.widget.EditText", "android.widget.AutoCompleteTextView"]:
        el = d(className=cls)
        if el.exists:
            print(f"  Found {cls}: {el.info}")
            search_box = el
            break

print("\n=== Step 2: Click on search box ===")
if search_box.exists:
    search_box.click()
    time.sleep(1)
    focused = search_box.info.get('focused', False)
    print(f"  Focused after click: {focused}")
else:
    print("  Search box not found! Trying ADB tap at center-top...")
    # Tap near top center where search bar usually is
    d.click(540, 80)
    time.sleep(1)

print("\n=== Step 3: Try set_text (PASTE mode) ===")
try:
    search_box2 = d(resourceId=search_id)
    if not search_box2.exists:
        search_box2 = d(className="android.widget.EditText")
    search_box2.set_text(SEARCH_TEXT)
    time.sleep(1)
    text_after = d(resourceId=search_id).get_text() if d(resourceId=search_id).exists else ""
    print(f"  Text in box after set_text: '{text_after}'")
except Exception as e:
    print(f"  set_text FAILED: {e}")

print("\n=== Step 4: Try ADB send_keys ===")
try:
    # Clear first
    d.clear_text()
    time.sleep(0.5)
    d.send_keys(SEARCH_TEXT, clear=True)
    time.sleep(1)
    text_after = d(resourceId=search_id).get_text() if d(resourceId=search_id).exists else ""
    print(f"  Text in box after send_keys: '{text_after}'")
except Exception as e:
    print(f"  send_keys FAILED: {e}")

print("\n=== Step 5: Try ADB shell input text ===")
try:
    # First clear
    subprocess.run(
        f"adb -s {DEVICE} shell input keyevent KEYCODE_CTRL_A",
        shell=True, check=False
    )
    subprocess.run(
        f"adb -s {DEVICE} shell input keyevent KEYCODE_DEL",
        shell=True, check=False
    )
    time.sleep(0.5)
    result = subprocess.run(
        f"adb -s {DEVICE} shell input text {SEARCH_TEXT}",
        shell=True, capture_output=True, text=True
    )
    time.sleep(1)
    text_after = d(resourceId=search_id).get_text() if d(resourceId=search_id).exists else "not found"
    print(f"  Result stderr: {result.stderr}")
    print(f"  Text in box after adb input text: '{text_after}'")
except Exception as e:
    print(f"  ADB input FAILED: {e}")

print("\n=== DONE ===")
