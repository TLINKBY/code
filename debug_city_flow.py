import uiautomator2 as u2
import time

d = u2.connect()
d.app_start("ctrip.android.view", stop=True)
time.sleep(7)

# Click 机票
d(description="机票").click()
time.sleep(4)

# Click 单程
if d(text="单程").exists:
    d(text="单程").click()
    time.sleep(1)

# Select departure city
d(description="depart city").click()
time.sleep(2.5)
search_input = d(className="android.widget.EditText")
if search_input.exists():
    search_input.click()
    d.send_keys("成都", clear=True)
    time.sleep(3)
    result = d(description="城市页第1条搜索结果")
    if not result.exists():
        result = d(textContains="成都")
    result.click()
    print("Selected 成都 as departure")
    time.sleep(2)

# NOW: Check what screen we're on after selecting departure
print("\n=== After departure city selected, what's on screen? ===")
edit_text = d(className="android.widget.EditText")
if edit_text.exists():
    print("EditText found! The app auto-opened arrival city selector!")
    print(f"EditText text: '{edit_text.info.get('text', '')}'")
    # We're already on city search page, just type arrival city
    edit_text.click()
    d.send_keys("东京", clear=True)
    time.sleep(3)
    result = d(description="城市页第1条搜索结果")
    if not result.exists():
        result = d(textContains="东京")
    if result.exists():
        result.click()
        print("Selected 东京 as arrival (auto-opened)")
    time.sleep(2)
else:
    print("No EditText found. Still on search page.")
    arr_btn = d(description="arrival city")
    if arr_btn.exists():
        print("Found arrival city button normally")
    else:
        print("arrival city button NOT found either!")

# Dump current state
print("\n=== Current screen state ===")
for el in d(className="android.widget.TextView"):
    if el.exists:
        t = el.info.get('text', '').strip()
        if t and len(t) < 40:
            print(f"  TEXT: '{t}'")
