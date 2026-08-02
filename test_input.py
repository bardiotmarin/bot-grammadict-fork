import uiautomator2 as u2
import time

d = u2.connect("127.0.0.1:21523")

# Click to focus
et = d(resourceId="com.instagram.android:id/action_bar_search_edit_text")
et.click()
time.sleep(0.5)

# Clear using UIAutomator set_text with empty string
et.set_text("")
time.sleep(0.3)
print("After clear:", repr(et.get_text()))

# Now use ADB input text (spaces as %s)
target = "Lavo Las Vegas"
adb_text = target.replace(" ", "%s")
d.shell(f"input text {adb_text}")
time.sleep(1.5)
print("After ADB input text:", repr(et.get_text()))
