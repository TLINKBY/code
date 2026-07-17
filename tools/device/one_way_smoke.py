import uiautomator2 as u2
import time
d = u2.connect()
d.app_start("ctrip.android.view", stop=True)
time.sleep(7)
d(text="机票").click()
time.sleep(4)
print("Looking for '单程' tab...")
one_way = d(text="单程")
if one_way.exists:
    one_way.click()
    print("Clicked 单程")
else:
    print("单程 not found")
