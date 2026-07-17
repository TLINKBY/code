import uiautomator2 as u2
import time
d = u2.connect()
d.app_start("ctrip.android.view", stop=True)
time.sleep(7)
d(text="机票").click()
time.sleep(4)
print("Clicking search directly without changing cities (assuming already Chengdu to Tokyo)...")
inquire_btn = d(description="do inquire") or d(text="查 询") or d(text="查询")
if inquire_btn.exists(timeout=2):
    inquire_btn.click()
    print("Clicked inquire button")
else:
    d.click(500, 824)
    print("Clicked coordinate 500, 824")
time.sleep(6)
d.screenshot(filename="static/generated/intl_search.png")
print("Saved static/generated/intl_search.png")
