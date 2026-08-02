import uiautomator2 as u2
import time
import xml.etree.ElementTree as ET
import re
import sys

# Change standard output encoding
sys.stdout.reconfigure(encoding='utf-8')

d = u2.connect('127.0.0.1:21523')

print("2. Dumping True Search Screen...")
xml_str = d.dump_hierarchy()
try:
    with open('dump_true_search.xml', 'w', encoding='utf-8') as f:
        f.write(xml_str)
        
    nodes = re.findall(r'<node\s+([^>]+>)', xml_str)
    for node in nodes:
        if 'search' in node.lower() or 'edittext' in node.lower() or 'autocompletetextview' in node.lower():
            cls_match = re.search(r'class="(.*?)"', node)
            cls = cls_match.group(1) if cls_match else "N/A"
            text_match = re.search(r'text="(.*?)"', node)
            text = text_match.group(1) if text_match else "N/A"
            res_match = re.search(r'resource-id="(.*?)"', node)
            res = res_match.group(1) if res_match else "N/A"
            
            print(f"Class: {cls} | ID: {res}")
            
except Exception as e:
    print("XML error:", e)
