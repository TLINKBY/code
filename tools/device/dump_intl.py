import uiautomator2 as u2
import re
d = u2.connect()
print("Dumping all text on screen:")
for el in d(className="android.widget.TextView"):
    if el.exists:
        text = el.info.get('text', '').strip()
        if text:
            print(f"TEXT: '{text}' at Y={el.info.get('bounds',{}).get('top')}")
