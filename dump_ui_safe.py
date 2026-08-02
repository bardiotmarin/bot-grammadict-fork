import uiautomator2 as u2

d = u2.connect('127.0.0.1:21523')
xml_str = d.dump_hierarchy()
with open('dump_current_safe.xml', 'w', encoding='utf-8') as f:
    f.write(xml_str)
print("Dumped")
