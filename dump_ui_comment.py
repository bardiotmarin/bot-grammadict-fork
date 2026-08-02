import uiautomator2 as u2
import xml.dom.minidom

def dump_ui():
    d = u2.connect()
    xml_str = d.dump_hierarchy()
    
    # Parse XML and pretty print it
    dom = xml.dom.minidom.parseString(xml_str.encode('utf-8'))
    pretty_xml_as_string = dom.toprettyxml()
    
    with open('ui_dump_comment.xml', 'w', encoding='utf-8') as f:
        f.write(pretty_xml_as_string)
        
    print("UI dumped to ui_dump_comment.xml")
    
if __name__ == "__main__":
    dump_ui()
