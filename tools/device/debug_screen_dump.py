import uiautomator2 as u2
import time

d = u2.connect()
print("Dumping all text with Y coordinates on current screen:")
for el in d(className="android.widget.TextView"):
    try:
        if el.exists:
            text = el.info.get('text', '').strip()
            bounds = el.info.get('bounds', {})
            if text:
                y_center = (bounds.get('top', 0) + bounds.get('bottom', 0)) / 2
                print(f"Y={y_center:7.0f} | TEXT: '{text}'")
    except:
        pass

d.screenshot(filename="static/debug_after_search.png")
print("\nScreenshot saved to static/debug_after_search.png")
