import uiautomator2 as u2
import time
import xml.etree.ElementTree as ET
import re

d = u2.connect('127.0.0.1:21523')
print("Connected")
d.app_start("com.instagram.android")
time.sleep(3)
d(description="Search and explore").click_exists()
d(descriptionMatches=".*[Ss]earch.*").click_exists()
time.sleep(1)

xml_str = d.dump_hierarchy()
try:
    root = ET.fromstring(xml_str)
    for node in root.iter('node'):
        text = node.get('text', '')
        content_desc = node.get('content-desc', '')
        resource_id = node.get('resource-id', '')
        css_class = node.get('class', '')
        
        if re.search(r'search', text, re.IGNORECASE) or re.search(r'search', content_desc, re.IGNORECASE) or re.search(r'search', resource_id, re.IGNORECASE) or 'EditText' in css_class or 'AutoCompleteTextView' in css_class:
            print(f"Class: {css_class}\nID: {resource_id}\nText: {text}\nDesc: {content_desc}\nBounds: {node.get('bounds')}\n---")
except Exception as e:
    print("XML error:", e)
