import uiautomator2 as u2
import time
import re

d = u2.connect()
d.app_start("ctrip.android.view", stop=True)
time.sleep(7)

# Navigate
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

# Click search (use the proper selector chain)
for name, sel in [
    ("text='查 询'", d(text="查 询")),
    ("text='查询'", d(text="查询")),
    ("textContains='查询'", d(textContains="查询")),
]:
    if sel.exists(timeout=2):
        print(f"Clicking search via {name}")
        sel.click()
        break
else:
    print("Clicking search at coordinate (540, 1234)")
    d.click(540, 1234)

# Wait for results to load
print("Waiting 8 seconds for results to load...")
time.sleep(8)

# Now dump the screen with Y coordinates
print("\n========== SCREEN TEXT DUMP WITH Y ==========")
views = []
for el in d(className="android.widget.TextView"):
    try:
        if el.exists:
            text = el.info.get('text', '').strip()
            bounds = el.info.get('bounds')
            if text and bounds:
                y_center = (bounds['top'] + bounds['bottom']) / 2
                views.append({'text': text, 'y_center': y_center, 'top': bounds['top'], 'bottom': bounds['bottom']})
                print(f"  Y_center={y_center:6.0f} top={bounds['top']:5d} bot={bounds['bottom']:5d} | '{text}'")
    except:
        pass

# Now simulate parse_screen_flights row grouping with threshold=80
print("\n========== ROW GROUPING (threshold=80) ==========")
views.sort(key=lambda x: x['y_center'])
rows = []
current_row = []
for v in views:
    if not current_row:
        current_row.append(v)
    else:
        if abs(v['y_center'] - current_row[-1]['y_center']) <= 80:
            current_row.append(v)
        else:
            rows.append(current_row)
            current_row = [v]
if current_row:
    rows.append(current_row)

for i, row in enumerate(rows):
    texts = [v['text'] for v in row]
    y_min = min(v['y_center'] for v in row)
    y_max = max(v['y_center'] for v in row)
    
    prices = [t for t in texts if t.replace("¥","").replace(" ","").strip().isdigit() and 100 <= int(t.replace("¥","").replace(" ","").strip()) < 20000]
    times_found = [t for t in texts if re.match(r'^\d{2}:\d{2}$', t)]
    
    status = "✅ VALID" if prices and len(times_found) >= 2 else "❌ SKIP"
    print(f"\nRow {i} (Y: {y_min:.0f}-{y_max:.0f}) [{status}]")
    print(f"  Texts: {texts}")
    print(f"  Prices: {prices}, Times: {times_found}")
