import uiautomator2 as u2
import time
import xml.etree.ElementTree as ET

d = u2.connect()
d.app_start("ctrip.android.view", stop=True)
time.sleep(7)

d(description="机票").click()
time.sleep(4)
if d(text="单程").exists:
    d(text="单程").click()
    time.sleep(1)

# Select cities
d(description="depart city").click()
time.sleep(2.5)
d(className="android.widget.EditText").click()
d.send_keys("成都", clear=True)
time.sleep(3)
r = d(description="城市页第1条搜索结果")
if not r.exists():
    r = d(textContains="成都")
r.click()
time.sleep(2)

d(description="arrival city").click()
time.sleep(2.5)
d(className="android.widget.EditText").click()
d.send_keys("东京", clear=True)
time.sleep(3)
r = d(description="城市页第1条搜索结果")
if not r.exists():
    r = d(textContains="东京")
r.click()
time.sleep(2)

# Open calendar
d(description="depart date").click()
time.sleep(3)

# Swipe to find September
for _ in range(5):
    header = d(textContains="2026年9月")
    if header.exists():
        break
    d.swipe(540, 1500, 540, 800, duration=0.3)
    time.sleep(1)

# Dump hierarchy around September area
xml_str = d.dump_hierarchy()
with open("calendar_hierarchy.xml", "w", encoding="utf-8") as f:
    f.write(xml_str)
print("Saved full hierarchy to calendar_hierarchy.xml")

# Now parse the XML and find elements with content-desc containing dates or "26"
root = ET.fromstring(xml_str)
print("\n=== Elements with description containing '26' ===")
for elem in root.iter():
    desc = elem.get('content-desc', '')
    text = elem.get('text', '')
    bounds = elem.get('bounds', '')
    clazz = elem.get('class', '')
    if '26' in desc or '26' in text:
        print(f"  class={clazz} text='{text}' desc='{desc}' bounds={bounds}")

print("\n=== Elements with description containing '9月26' or 'Sep' ===")
for elem in root.iter():
    desc = elem.get('content-desc', '')
    if '9月26' in desc or '09-26' in desc or 'Sep' in desc:
        print(f"  class={elem.get('class','')} desc='{desc}' bounds={elem.get('bounds','')}")

print("\n=== Clickable elements in Y range 700-1800 ===")
for elem in root.iter():
    bounds = elem.get('bounds', '')
    clickable = elem.get('clickable', 'false')
    desc = elem.get('content-desc', '')
    text = elem.get('text', '')
    if bounds and clickable == 'true' and (desc or text):
        # Parse bounds [x1,y1][x2,y2]
        try:
            parts = bounds.replace('][', ',').replace('[', '').replace(']', '').split(',')
            y1 = int(parts[1])
            if 700 <= y1 <= 1800:
                print(f"  Y={y1:5d} class={elem.get('class','')} text='{text}' desc='{desc}' bounds={bounds}")
        except:
            pass
