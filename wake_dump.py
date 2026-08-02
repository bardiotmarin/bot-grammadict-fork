import uiautomator2 as u2
import time
import xml.etree.ElementTree as ET
import re

d = u2.connect('127.0.0.1:21523')
d.screen_on()
d.session("com.instagram.android")
time.sleep(2)

tab = d(descriptionMatches="(?i).*search.*")
if tab.exists:
    tab.click()
    print("Clicked Search Tab")
else:
    print("Search Tab not found")
        
time.sleep(2)
xml = d.dump_hierarchy()
with open('dump_search_investigation.xml', 'w', encoding='utf-8') as f:
    f.write(xml)

nodes = re.findall(r'<node\s+([^>]+>)', xml)
for node in nodes:
    if 'search' in node.lower() or 'edittext' in node.lower() or 'autocompletetextview' in node.lower():
        cls_match = re.search(r'class="(.*?)"', node)
        cls = cls_match.group(1) if cls_match else "N/A"
        
        text_match = re.search(r'text="(.*?)"', node)
        text = text_match.group(1) if text_match else "N/A"
        
        res_match = re.search(r'resource-id="(.*?)"', node)
        res = res_match.group(1) if res_match else "N/A"
        
        desc_match = re.search(r'content-desc="(.*?)"', node)
        desc = desc_match.group(1) if desc_match else "N/A"
        
        bounds_match = re.search(r'bounds="(.*?)"', node)
        bounds = bounds_match.group(1) if bounds_match else "N/A"
        
        print(f"Class: {cls}\nID: {res}\nText: {text}\nDesc: {desc}\nBounds: {bounds}\n---")
