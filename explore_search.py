import uiautomator2 as u2
import time
import xml.etree.ElementTree as ET
import re

d = u2.connect('127.0.0.1:21523')

print("1. Clicking Search tab from Home/Anywhere...")
tab = d(descriptionMatches="(?i).*search.*explore.*")
if not tab.exists:
    tab = d(descriptionMatches="(?i).*search.*")
if tab.exists:
    tab.click()
    time.sleep(3)

print("--- Dump of Explore Screen ---")
nodes = re.findall(r'<node\s+([^>]+>)', d.dump_hierarchy())
for node in nodes:
    if 'search' in node.lower() or 'edittext' in node.lower() or 'autocompletetextview' in node.lower() or 'textview' in node.lower():
        cls_match = re.search(r'class="(.*?)"', node)
        cls = cls_match.group(1) if cls_match else "N/A"
        
        text_match = re.search(r'text="(.*?)"', node)
        text = text_match.group(1) if text_match else "N/A"
        
        res_match = re.search(r'resource-id="(.*?)"', node)
        res = res_match.group(1) if res_match else "N/A"
        
        if 'search' in str(text).lower() or 'search' in str(res).lower() or 'edittext' in cls.lower() or 'autocompletetextview' in cls.lower():
            print(f"Class: {cls} | ID: {res} | Text: {text}")

print("\n2. Clicking on the Search field in Explore...")
# Click the search field to expand the true search view
d(resourceId="com.instagram.android:id/action_bar_search_edit_text").click_exists()
time.sleep(2)

print("--- Dump of True Search Screen ---")
nodes = re.findall(r'<node\s+([^>]+>)', d.dump_hierarchy())
for node in nodes:
    if 'search' in node.lower() or 'edittext' in node.lower() or 'autocompletetextview' in node.lower():
        cls_match = re.search(r'class="(.*?)"', node)
        cls = cls_match.group(1) if cls_match else "N/A"
        text_match = re.search(r'text="(.*?)"', node)
        text = text_match.group(1) if text_match else "N/A"
        res_match = re.search(r'resource-id="(.*?)"', node)
        res = res_match.group(1) if res_match else "N/A"
        if 'search' in str(text).lower() or 'search' in str(res).lower() or 'edittext' in cls.lower() or 'autocompletetextview' in cls.lower():
            print(f"Class: {cls} | ID: {res} | Text: {text}")
