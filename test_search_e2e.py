"""
End-to-end test of the full search navigation flow used by GramAddict.
Tests that the bot can navigate to Search and type a hashtag.
"""
import sys
sys.path.insert(0, '.')

import uiautomator2 as u2
from time import sleep

DEVICE = "127.0.0.1:21523"
APP_ID = "com.instagram.android"
HASHTAG = "deephouse"

d = u2.connect(DEVICE)

# Navigate to Home first (simulate bot startup)
print("[1] Navigating to Home tab...")
home_btn = d(descriptionMatches="(?i).*home.*")
if home_btn.exists:
    home_btn.click()
    sleep(2)
    print("  -> Arrived at Home")
else:
    print("  -> Home button not found!")

# Navigate to Search tab (simulate bot navigateToSearch)
print("[2] Navigating to Search tab...")
search_btn = d(descriptionMatches="(?i).*search.*explore.*")
if not search_btn.exists:
    search_btn = d(descriptionMatches="(?i).*search.*")
if search_btn.exists:
    search_btn.click()
    sleep(2)
    print("  -> Arrived at Search/Explore")
else:
    print("  -> Search button not found!")

# Find the EditText by resource ID
search_id = f"{APP_ID}:id/action_bar_search_edit_text"
search_box = d(resourceId=search_id)
print(f"[3] Search EditText exists: {search_box.exists}")

# Click to focus
if search_box.exists:
    search_box.click()
    sleep(1)
    print(f"  -> Focused: {search_box.info.get('focused')}")
else:
    print("  -> Not found, trying EditText class...")
    et = d(className="android.widget.EditText")
    if et.exists:
        et.click()
        sleep(1)
        search_box = et

# Type the hashtag using PASTE mode (same as set_text)
print(f"[4] Typing '{HASHTAG}' via set_text (PASTE mode)...")
search_box = d(resourceId=search_id)
if not search_box.exists:
    search_box = d(className="android.widget.EditText")

if search_box.exists:
    search_box.set_text(HASHTAG)
    sleep(2)
    text_in_box = d(resourceId=search_id).get_text() if d(resourceId=search_id).exists else ""
    print(f"  -> Text in box: '{text_in_box}'")
    
    # Check if search results appeared
    row_hashtag = d(resourceId=f"{APP_ID}:id/row_hashtag_textview_tag_name")
    row_user = d(resourceId=f"{APP_ID}:id/row_search_user_username")
    if row_hashtag.exists or row_user.exists:
        print("[OK] Search results appeared!")
        if row_hashtag.exists:
            print(f"  -> Hashtag row found: {row_hashtag.get_text()}")
    else:
        print("[WARN] No search rows found. UI may need more time.")
else:
    print("[FAIL] Could not find the search box!")

print("\n=== Test DONE ===")
