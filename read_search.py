import xml.etree.ElementTree as ET

try:
    tree = ET.parse('dump_search_debug.xml')
    root = tree.getroot()

    print("--- ALL EDITABLE/CLICKABLE TEXT/DESC NODES ---")
    for node in root.iter('node'):
        text = node.get('text', '')
        desc = node.get('content-desc', '')
        res_id = node.get('resource-id', '')
        cls = node.get('class', '')
        
        if 'search' in text.lower() or 'search' in desc.lower() or 'Search' in text or 'EditText' in cls or 'TextView' in cls or node.get('focused') == 'true':
            # specifically we are interested in anything resembling the search bar
            if node.get('clickable') == 'true' or node.get('focusable') == 'true' or 'search' in text.lower() or 'search' in desc.lower() or 'search' in res_id.lower():
                print(f"Class: {cls}\nID: {res_id}\nText: {text}\nDesc: {desc}\nFocused: {node.get('focused')}\nBounds: {node.get('bounds')}\n---")
except Exception as e:
    print("Error:", e)
