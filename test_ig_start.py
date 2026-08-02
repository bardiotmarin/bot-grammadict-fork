from time import sleep
import uiautomator2 as u2
import subprocess

# Connect to MEmu
d = u2.connect("127.0.0.1:21523")

print("Launching IG via ADB...")
cmd = "adb -s 127.0.0.1:21523 shell monkey -p com.instagram.android -c android.intent.category.LAUNCHER 1"
subprocess.run(cmd, shell=True)

sleep(1)
print(f"Current app (1s): {d.app_current()['package']}")
sleep(3)
print(f"Current app (4s): {d.app_current()['package']}")
sleep(4)
print(f"Current app (8s): {d.app_current()['package']}")
