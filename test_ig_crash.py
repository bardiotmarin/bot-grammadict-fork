from time import sleep
import uiautomator2 as u2

# Connect to MEmu
d = u2.connect("127.0.0.1:21523")
print(f"Initial app: {d.app_current()['package']}")

print("Starting Instagram...")
# Start using the identical method
d.app_start("com.instagram.android")
sleep(3)

print(f"Current app after start: {d.app_current()['package']}")

print("Running dump_hierarchy...")
d.dump_hierarchy()
print(f"Current app after dump_hierarchy: {d.app_current()['package']}")

print("Running fastinput_ime config...")
d.set_fastinput_ime(True)
print(f"Current app after fastinput_ime: {d.app_current()['package']}")
