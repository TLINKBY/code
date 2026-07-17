import uiautomator2 as u2
import time

d = u2.connect()
d.app_start("ctrip.android.view", stop=True)
time.sleep(7)

# Navigate to flights search page
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
print("=== Opening calendar ===")
date_sel = d(description="depart date")
if date_sel.exists(timeout=3):
    date_sel.click()
else:
    d.click(540, 600)
time.sleep(3)

# Dump ALL calendar elements
print("\n=== CALENDAR DUMP (all elements with Y) ===")
for el in d(className="android.widget.TextView"):
    try:
        if el.exists:
            text = el.info.get('text', '').strip()
            bounds = el.info.get('bounds', {})
            if text:
                y = (bounds.get('top', 0) + bounds.get('bottom', 0)) / 2
                x = (bounds.get('left', 0) + bounds.get('right', 0)) / 2
                print(f"  X={x:6.0f} Y={y:6.0f} | '{text}'")
    except:
        pass

# Now try to find "2026年9月" header and then find "26" below it
print("\n=== Looking for September header ===")
header = d(textContains="2026年9月")
if header.exists():
    h_bounds = header.info.get('bounds', {})
    h_top = h_bounds.get('top', 0)
    h_bottom = h_bounds.get('bottom', 0)
    print(f"Found '2026年9月' at Y={h_top}-{h_bottom}")
    
    # Find all "26" elements and check which one is below the September header
    target_elements = d(text="26")
    print(f"\nFound {target_elements.count} elements with text '26'")
    for i in range(target_elements.count):
        el = target_elements[i]
        if el.exists:
            b = el.info.get('bounds', {})
            el_y = b.get('top', 0)
            el_x = (b.get('left', 0) + b.get('right', 0)) / 2
            print(f"  '26' #{i}: X={el_x:.0f} Y_top={el_y} (below header: {el_y > h_bottom})")
else:
    print("September header NOT found! Need to swipe.")
    # Try swiping to find it
    for _ in range(5):
        d.swipe(540, 1500, 540, 800, duration=0.3)
        time.sleep(1)
        header = d(textContains="2026年9月")
        if header.exists():
            h_bounds = header.info.get('bounds', {})
            print(f"Found after swipe at Y={h_bounds.get('top')}-{h_bounds.get('bottom')}")
            break

d.screenshot(filename="static/generated/debug_calendar.png")
print("\nScreenshot saved")
