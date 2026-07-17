import uiautomator2 as u2
import time

d = u2.connect()
print("Connected to device")

# Step 1: Force restart Ctrip
print("\n=== Step 1: Restart Ctrip ===")
d.app_start("ctrip.android.view", stop=True)
time.sleep(7)

# Step 2: Dismiss ads
print("\n=== Step 2: Dismiss ads ===")
if d(textContains="允许").exists(timeout=1):
    d(textContains="允许").click()
    time.sleep(1)

# Step 3: Find 机票 button
print("\n=== Step 3: Find 机票 button ===")
flight_icon = d(description="机票")
if flight_icon.exists():
    print(f"Found by description='机票'")
else:
    flight_icon = d(text="机票")
    if flight_icon.exists():
        print(f"Found by text='机票'")
    else:
        print("ERROR: Cannot find 机票 button!")
        # Dump what's on screen
        for el in d(className="android.widget.TextView"):
            if el.exists:
                t = el.info.get('text', '').strip()
                if t:
                    print(f"  Screen text: '{t}'")
        exit(1)

flight_icon.click()
time.sleep(4)
print("Clicked 机票, now on search page")

# Step 4: Click 单程
print("\n=== Step 4: Click 单程 ===")
one_way = d(text="单程")
if one_way.exists:
    one_way.click()
    print("Clicked 单程")
    time.sleep(1)
else:
    print("单程 not found on screen")

# Dump search page state
print("\n=== Dump search page ===")
for el in d(className="android.widget.TextView"):
    if el.exists:
        t = el.info.get('text', '').strip()
        b = el.info.get('bounds', {})
        if t and len(t) < 30:
            print(f"  TEXT: '{t}' Y={b.get('top', '?')}-{b.get('bottom', '?')}")

# Step 5: Select departure city
print("\n=== Step 5: Select departure city ===")
dep_btn = d(description="depart city")
if dep_btn.exists():
    dep_btn.click()
    print("Clicked depart city selector")
else:
    print("ERROR: depart city not found!")
    exit(1)
time.sleep(2)
d(className="android.widget.EditText").set_text("成都")
time.sleep(3)
suggestion = d(textContains="成都")
if suggestion.exists:
    suggestion.click()
    print("Selected 成都")
else:
    print("ERROR: 成都 suggestion not found")
time.sleep(2)

# Step 6: Select arrival city
print("\n=== Step 6: Select arrival city ===")
arr_btn = d(description="arrival city")
if arr_btn.exists():
    arr_btn.click()
    print("Clicked arrival city selector")
else:
    print("ERROR: arrival city not found!")
    exit(1)
time.sleep(2)
d(className="android.widget.EditText").set_text("东京")
time.sleep(3)
suggestion = d(textContains="东京")
if suggestion.exists:
    suggestion.click()
    print("Selected 东京")
else:
    print("ERROR: 东京 suggestion not found")
time.sleep(2)

# Step 7: Check if we're still on search page after city selection
print("\n=== Step 7: Search page after city selection ===")
for el in d(className="android.widget.TextView"):
    if el.exists:
        t = el.info.get('text', '').strip()
        b = el.info.get('bounds', {})
        if t and len(t) < 30:
            print(f"  TEXT: '{t}' Y={b.get('top', '?')}-{b.get('bottom', '?')}")

# Step 8: Try to find the search/inquire button
print("\n=== Step 8: Find search button ===")
candidates = [
    ("description='do inquire'", d(description="do inquire")),
    ("text='查 询'", d(text="查 询")),
    ("text='查询'", d(text="查询")),
    ("text='搜索'", d(text="搜索")),
    ("text='搜 索'", d(text="搜 索")),
    ("textContains='查'", d(textContains="查")),
    ("textContains='搜索'", d(textContains="搜索")),
]
for name, sel in candidates:
    if sel.exists:
        info = sel.info
        bounds = info.get('bounds', {})
        print(f"  FOUND: {name} at Y={bounds.get('top', '?')}-{bounds.get('bottom', '?')}")
    else:
        print(f"  NOT FOUND: {name}")

# Step 9: Take a screenshot of the current search page
print("\n=== Step 9: Screenshot ===")
d.screenshot(filename="static/debug_search_page.png")
print("Saved debug_search_page.png")
