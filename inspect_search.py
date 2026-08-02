import uiautomator2 as u2
import time

d = u2.connect("127.0.0.1:21523")

# Clear and type search
et = d(resourceId="com.instagram.android:id/action_bar_search_edit_text")
et.clear_text()
time.sleep(0.3)
d.send_keys("hugelthug", clear=True)
time.sleep(2.5)

xml = d.dump_hierarchy()

# Print ALL unique resource-ids containing 'search'
seen = set()
for part in xml.split("<node "):
    if "resource-id=" not in part:
        continue
    try:
        rid_start = part.index('resource-id="') + 13
        rid_end = part.index('"', rid_start)
        rid = part[rid_start:rid_end]
        txt_start = part.index('text="') + 6
        txt_end = part.index('"', txt_start)
        txt = part[txt_start:txt_end]
        cls_start = part.index('class="') + 7
        cls_end = part.index('"', cls_start)
        cls = part[cls_start:cls_end]
        if rid not in seen:
            seen.add(rid)
            if "search" in rid.lower() or (txt and any(c in txt.lower() for c in ["hugel","thug"])):
                print(f"ID={rid!r}  TEXT={txt!r}  CLASS={cls!r}")
    except ValueError:
        pass

print("\n--- All unique resource-ids in page ---")
for rid in sorted(seen):
    print(rid)
