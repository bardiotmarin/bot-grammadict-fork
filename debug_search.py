import uiautomator2 as u2
import xml.etree.ElementTree as ET
import re
import time

d = u2.connect('127.0.0.1:21523')

print("Ensuring we find the search box...")
# Attempt to click search icon first
search_tab = d(descriptionMatches="(?i).*search.*")
if search_tab.exists:
    search_tab.click()
    time.sleep(2)

xml_str = d.dump_hierarchy()
try:
    with open('dump_search_investigation.xml', 'w', encoding='utf-8') as f:
        f.write(xml_str)
        
    root = ET.fromstring(xml_str)
    print("--- POTENTIAL SEARCH FIELDS ---")
    for node in root.iter('node'):
        text = node.get('text', '')
        desc = node.get('content-desc', '')
        res_id = node.get('resource-id', '')
        cls = node.get('class', '')
        
        if 'search' in text.lower() or 'search' in desc.lower() or 'search' in res_id.lower() or 'edittext' in cls.lower() or 'autocompletetextview' in cls.lower():
            print(f"Class: {cls}")
            print(f"ID: {res_id}")
            print(f"Text: {text}")
            print(f"Desc: {desc}")
            print(f"Bounds: {node.get('bounds')}")
            print(f"Focusable: {node.get('focusable')}")
            print(f"Clickable: {node.get('clickable')}")
            print("---")
except Exception as e:
    print("Error:", e)
