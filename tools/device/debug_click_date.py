import uiautomator2 as u2
import time

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

# From hierarchy data (UN-SWIPED):
# Header "2026年9月": Y=691-769
# Week 1: Y=775-953 (178px)
# Week 2: Y=952-1130
# Week 3: Y=1129-1307
# Week 4: Y=1306-1484  ← Sept 26 is here
# Week 5: Y=1483-1661
# Clickable area: X=13-1067 (width=1054)
# Column width: 1054/7 = 150.57

# September 1, 2026 = Tuesday
# Test BOTH calendar layouts:

# Sunday-first: Sept 26 (Saturday) = column 6, Week 4
# Monday-first: Sept 26 (Saturday) = column 5, Week 4

# First, NO swiping - use original positions
print("=== Test 1: Sunday-first click (column 6) ===")
col6_x = int(13 + (6 + 0.5) * (1054 / 7))  # ~992
week4_y = int((1306 + 1484) / 2)  # ~1395
print(f"Click at ({col6_x}, {week4_y})")
d.click(col6_x, week4_y)
time.sleep(3)

# Check if calendar closed
if d(text="查 询").exists(timeout=2) or d(textMatches="查.询").exists(timeout=1):
    print("Calendar CLOSED! Sunday-first is correct!")
    # Read the date shown on search page
    for el in d(className="android.widget.TextView"):
        if el.exists:
            t = el.info.get('text', '').strip()
            if '月' in t and '日' in t:
                print(f"Selected date: {t}")
                break
else:
    print("Calendar still open. Sunday-first is WRONG.")
    print("Trying Monday-first...")
    
    # Re-open calendar if needed (press back and try again)
    # Actually calendar might still be open, just click Monday-first position
    col5_x = int(13 + (5 + 0.5) * (1054 / 7))  # ~841
    print(f"\n=== Test 2: Monday-first click (column 5) at ({col5_x}, {week4_y}) ===")
    d.click(col5_x, week4_y)
    time.sleep(3)
    
    if d(text="查 询").exists(timeout=2) or d(textMatches="查.询").exists(timeout=1):
        print("Calendar CLOSED! Monday-first is correct!")
        for el in d(className="android.widget.TextView"):
            if el.exists:
                t = el.info.get('text', '').strip()
                if '月' in t and '日' in t:
                    print(f"Selected date: {t}")
                    break
    else:
        print("Calendar STILL open. Neither layout worked!")
        # Dump what's on screen
        for el in d(className="android.widget.TextView"):
            try:
                if el.exists:
                    t = el.info.get('text', '').strip()
                    if t:
                        print(f"  Screen: '{t}'")
            except:
                pass
