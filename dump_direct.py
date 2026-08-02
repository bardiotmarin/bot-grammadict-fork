import uiautomator2 as u2
import xml.etree.ElementTree as ET

d = u2.connect('127.0.0.1:21523')
xml = d.dump_hierarchy()
with open('dump_now.xml', 'w', encoding='utf-8') as f:
    f.write(xml)

root = ET.fromstring(xml)
print("--- RAW NODES ---")
for node in root.iter('node'):
    text = node.get('text', '')
    desc = node.get('content-desc', '')
    res_id = node.get('resource-id', '')
    cls = node.get('class', '')
    
    if text: print(f"Text: {text}")
    elif desc: print(f"Desc: {desc}")
    elif 'edit' in cls.lower() or 'search' in res_id.lower():
        print(f"Class: {cls} | ID: {res_id}")
