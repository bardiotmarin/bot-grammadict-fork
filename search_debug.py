import uiautomator2 as u2
import time
import re

d = u2.connect('127.0.0.1:21523')

print("Clicking Search tab...")
tab = d(descriptionMatches="(?i).*search.*")
if tab.exists:
    tab.click()
    time.sleep(2)

xml = d.dump_hierarchy()
with open('dump_search_debug.xml', 'w', encoding='utf-8') as f:
    f.write(xml)

nodes = re.findall(r'<node\s+([^>]+>)', xml)
print("--- POTENTIAL SEARCH FIELDS ---")
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
        
        print(f"Class: {cls}\nID: {res}\nText: {text}\nDesc: {desc}\n---")
