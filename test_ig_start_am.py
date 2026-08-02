from time import sleep
import uiautomator2 as u2

# Connect to MEmu
d = u2.connect("127.0.0.1:21523")

print("Launching IG via u2 app_start(use_monkey=True)...")
d.app_start("com.instagram.android", use_monkey=True)

sleep(1)
print(f"Current app (1s): {d.app_current()['package']}")
sleep(3)
print(f"Current app (4s): {d.app_current()['package']}")
sleep(4)
print(f"Current app (8s): {d.app_current()['package']}")
