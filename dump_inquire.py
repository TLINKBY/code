import uiautomator2 as u2
import re
d = u2.connect()
print("Dumping all UI elements to find search button:")
for el in d():
    if el.exists:
        text = el.info.get('text', '').strip()
        desc = el.info.get('contentDescription', '').strip()
        clazz = el.info.get('className', '')
        if text or desc:
            print(f"CLASS: {clazz} TEXT: '{text}' DESC: '{desc}' at Y={el.info.get('bounds',{}).get('top')}")
