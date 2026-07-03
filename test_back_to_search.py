import uiautomator2 as u2
import time
d = u2.connect()
d.app_start("ctrip.android.view", stop=True)
time.sleep(7)
d(text="机票").click()
time.sleep(4)
print("Dumping search page UI elements...")
for el in d():
    if el.exists:
        text = el.info.get('text', '').strip()
        desc = el.info.get('contentDescription', '').strip()
        if text or desc:
            print(f"TEXT: '{text}' DESC: '{desc}' BOUNDS: {el.info.get('bounds')}")
