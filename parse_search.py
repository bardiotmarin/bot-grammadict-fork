import xml.etree.ElementTree as ET
import re

tree = ET.parse('ui_dump_search.xml')
root = tree.getroot()

for node in root.iter('node'):
    text = node.get('text', '')
    content_desc = node.get('content-desc', '')
    resource_id = node.get('resource-id', '')
    css_class = node.get('class', '')
    
    if re.search(r'search', text, re.IGNORECASE) or re.search(r'search', content_desc, re.IGNORECASE) or re.search(r'search', resource_id, re.IGNORECASE) or css_class == 'android.widget.EditText':
        print(f"Class: {css_class}\nID: {resource_id}\nText: {text}\nDesc: {content_desc}\nBounds: {node.get('bounds')}\n---")
