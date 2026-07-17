import sys # 导入系统参数库
import os # 导入操作系统接口库
import time # 导入时间库，用于 sleep 延时（等待 App 动画）
import re # 导入正则表达式库，用于匹配字符串
import calendar # 导入日历库
import xml.etree.ElementTree as ET # 用于快速解析 Android UI hierarchy
import uiautomator2 as u2 # 导入核心自动化库 uiautomator2，用于操控安卓手机
from datetime import datetime # 导入时间日期处理类
from PIL import Image # 导入图像处理库，用于处理截图
from db import add_log # 导入我们自己的日志记录函数
from android_device import choose_device_serial, list_adb_devices, resolve_launcher_activity

BASE_SCREEN_WIDTH = 1080
BASE_SCREEN_HEIGHT = 2400
CTRIP_PACKAGE = "ctrip.android.view"
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(PROJECT_DIR, "static")
GENERATED_SCREENSHOT_DIR = os.path.join(STATIC_DIR, "generated")


def init_device():
    """
    初始化连接安卓设备。
    默认优先连接正在运行的模拟器；也可用 ANDROID_DEVICE_SERIAL 指定设备。
    """
    try:
        devices = list_adb_devices()
        requested_serial = os.environ.get("ANDROID_DEVICE_SERIAL", "").strip() or None
        serial = choose_device_serial(devices, requested_serial)
        add_log("INFO", f"Connecting to Android device: {serial}...")
        d = u2.connect(serial)
        add_log("INFO", f"Connected successfully ({serial}). Device: {d.device_info}")
        return d
    except Exception as e:
        add_log("ERROR", f"Failed to connect to device. Error: {e}") # 记录连接失败错误
        return None


def scaled_point(d, x, y):
    """把原真机 1080x2400 坐标换算到当前模拟器分辨率。"""
    try:
        width, height = d.window_size()
    except Exception:
        width = d.info.get("displayWidth", BASE_SCREEN_WIDTH)
        height = d.info.get("displayHeight", BASE_SCREEN_HEIGHT)
    return (
        int(x * width / BASE_SCREEN_WIDTH),
        int(y * height / BASE_SCREEN_HEIGHT),
    )


def click_scaled(d, x, y):
    click_x, click_y = scaled_point(d, x, y)
    d.click(click_x, click_y)
    return click_x, click_y


def start_ctrip_app(d):
    """冷启动携程，并确认其前台 Activity 已出现。"""
    activity = resolve_launcher_activity(d, CTRIP_PACKAGE)
    add_log("DEBUG", f"Starting {CTRIP_PACKAGE}/{activity}")
    d.app_start(CTRIP_PACKAGE, activity=activity, stop=True, wait=True)
    time.sleep(1)
    current = d.app_current()
    if current.get("package") != CTRIP_PACKAGE:
        raise RuntimeError(
            f"Ctrip did not enter foreground. Current app: {current.get('package')}"
        )

def configure_screen_awake(d):
    """
    尽量让手机在爬虫运行期间保持亮屏。
    这些命令在不同 Android 版本上支持程度不完全一致，所以失败只记日志，不中断爬虫。
    """
    commands = [
        ("settings put system screen_off_timeout 1800000", "Set screen timeout to 30 minutes"),
        ("settings put global stay_on_while_plugged_in 3", "Keep screen awake while charging over AC/USB"),
        ("svc power stayon true", "Enable stay-awake service flag"),
    ]
    for cmd, label in commands:
        try:
            d.shell(cmd)
            add_log("DEBUG", f"{label}: {cmd}")
        except Exception as e:
            add_log("WARNING", f"Failed to run screen-awake command '{cmd}': {e}")

def lockscreen_visible(d):
    """
    粗略判断当前是否停留在系统锁屏/PIN 输入页。
    不同 Android 版本文案不同，所以只做多 selector 兜底。
    """
    selectors = [
        d(textContains="输入 PIN"),
        d(textContains="输入密码"),
        d(textContains="PIN"),
        d(textContains="密码"),
        d(textContains="解锁"),
        d(textContains="紧急"),
        d(textContains="Emergency"),
        d(textContains="Enter PIN"),
        d(descriptionContains="解锁"),
        d(descriptionContains="Unlock"),
        d(resourceIdMatches=".*passwordEntry.*"),
        d(resourceIdMatches=".*pinEntry.*"),
        d(resourceIdMatches=".*keyguard.*"),
    ]
    for sel in selectors:
        try:
            if sel.exists(timeout=0.2):
                return True
        except Exception:
            pass
    return False

def unlock_with_pin_if_needed(d):
    """
    如果系统锁屏需要 PIN，使用环境变量 ANDROID_UNLOCK_PIN 解锁。
    PIN 不写入代码或数据库，避免泄露。
    """
    if not lockscreen_visible(d):
        return

    pin = os.environ.get("ANDROID_UNLOCK_PIN", "").strip()
    if not pin:
        add_log("WARNING", "Phone is on lock screen. Set ANDROID_UNLOCK_PIN or unlock manually.")
        return
    if not re.fullmatch(r"\d{4,12}", pin):
        add_log("WARNING", "ANDROID_UNLOCK_PIN must be a 4-12 digit PIN. Unlock manually.")
        return

    add_log("INFO", "Phone is locked. Entering PIN from ANDROID_UNLOCK_PIN...")
    try:
        # 优先用 adb input，避免把 PIN 记录到应用输入框。
        d.shell(f"input text {pin}")
        d.shell("input keyevent ENTER")
        time.sleep(1.5)
    except Exception as e:
        add_log("WARNING", f"Failed to enter unlock PIN: {e}")

def wake_and_unlock_device(d):
    """
    点亮屏幕并尽量解锁。
    无密码锁屏：上滑通常即可解锁。
    PIN 锁屏：需要设置环境变量 ANDROID_UNLOCK_PIN。
    """
    try:
        if not d.info.get('screenOn'):
            add_log("WARNING", "Screen turned off during crawl. Waking it up...")
            d.screen_on()
            time.sleep(1.5)

        # 不要在屏幕已经解锁时调用 d.unlock() 或无条件上滑。ensure_screen_on()
        # 会在主页、日历和航班列表中频繁调用；无条件手势会把当前页面一路滑到
        # 首页广告/内容流。先通过系统状态确认 Keyguard 是否真的显示。
        keyguard_showing = False
        try:
            policy_output = d.shell("dumpsys window policy").output
            keyguard_showing = bool(re.search(
                r"(?:showing|mIsShowing)\s*=\s*true",
                policy_output or "",
                re.IGNORECASE,
            ))
        except Exception as e:
            add_log("DEBUG", f"Failed to read keyguard state: {e}")
            keyguard_showing = lockscreen_visible(d)

        if keyguard_showing:
            add_log("INFO", "Lock screen detected. Unlocking device...")
            try:
                d.unlock()
            except Exception:
                d.swipe_ext("up", scale=0.8)
            time.sleep(1)
            unlock_with_pin_if_needed(d)
    except Exception as e:
        add_log("WARNING", f"Failed to verify/wake screen: {e}")

def ensure_screen_on(d):
    """
    关键操作前确认屏幕没有熄灭或停在锁屏页。
    """
    wake_and_unlock_device(d)

def unlock_device(d):
    """
    点亮屏幕并向上滑动解锁手机
    """
    wake_and_unlock_device(d)

def dismiss_ads(d):
    """
    负责在启动携程 App 时，自动关掉各种烦人的开屏广告、升级弹窗或促销弹窗
    """
    add_log("INFO", "Checking for splash ads or popups...")
    
    # 1. Skip button for splash ads (找开屏广告的“跳过”按钮)
    # 穷举了所有可能的“跳过”按钮的选择器（文字、描述、资源ID）
    skip_selectors = [
        d(textContains="跳过"),
        d(descriptionContains="跳过"),
        d(resourceIdMatches=".*skip.*"),
        d(resourceIdMatches=".*close_ad.*")
    ]
    for sel in skip_selectors:
        if sel.exists(timeout=1): # 如果 1 秒内发现这个按钮存在
            add_log("INFO", "Found splash ad skip button. Clicking...")
            sel.click() # 点击跳过
            time.sleep(2) # 给跳转动画留出 2 秒
            break
            
    # 2. Close buttons for homepage update / promotion popups (找主页的各种居中弹窗关闭按钮)
    close_selectors = [
        d(resourceId="ctrip.android.view:id/iv_close"),
        d(resourceId="ctrip.android.view:id/close_btn"),
        d(resourceId="ctrip.android.view:id/btn_close"),
        d(text="关闭"),
        d(description="关闭"),
        d(resourceId="ctrip.android.view:id/ib_close")
    ]
    for sel in close_selectors:
        if sel.exists(timeout=1):
            add_log("INFO", "Dismissing popup dialog...")
            sel.click() # 点击右上角或底部的 X 按钮
            time.sleep(1)

    # 首页红包促销浮层的 X 是自绘元素，不出现在 UI hierarchy 中。
    if d(text="点击收下").exists(timeout=0.5):
        click_x, click_y = scaled_point(d, 965, 515)
        add_log("INFO", f"Dismissing coupon popup at ({click_x}, {click_y})...")
        d.click(click_x, click_y)
        time.sleep(1)

def select_city(d, desc_selector, city_name):
    """
    负责在携程的主页面点击城市选择框，输入城市名，并在搜索结果里点击这个城市
    :param d: uiautomator2 对象
    :param desc_selector: 出发地或目的地框的内容描述 (content-desc)
    :param city_name: 要输入的城市名字，比如 "成都"
    """
    ensure_screen_on(d)

    # 进入机票页后目的地选择器可能延迟自动弹出。无论它何时出现，都先关闭，
    # 再从查询页上明确点击本次需要设置的城市字段。
    if "CityList" in d.app_current().get("activity", ""):
        add_log("INFO", "Closing unexpected city picker before selecting the requested field...")
        d.press("back")
        time.sleep(2)

    if d.app_current().get("package") != CTRIP_PACKAGE:
        add_log("ERROR", "Ctrip is not in the foreground before city selection; aborting.")
        return False

    selector = d(description=desc_selector) # 寻找出发地/目的地按钮
    if selector.exists(timeout=6):
        add_log("INFO", f"Clicking city selector '{desc_selector}' via description...")
        selector.click() # 点击它，进入城市搜索页面
    else:
        # 携程布局变化后，旧坐标可能落在通讯录等其他入口上。找不到明确控件时
        # 安全终止本次导航，不能在未知页面盲点坐标。
        add_log("ERROR", f"City selector '{desc_selector}' not found; refusing unsafe coordinate fallback.")
        return False
        
    time.sleep(2.5) # 给页面滑出动画一点时间
    
    # 验证是否成功进到了城市搜索页面，寻找输入框
    if d.app_current().get("package") != CTRIP_PACKAGE:
        add_log("ERROR", "Ctrip left the foreground while opening city search; aborting.")
        return False

    search_input = d(packageName=CTRIP_PACKAGE, className="android.widget.EditText")
    if not search_input.exists():
        search_input = d(resourceId="ctrip.android.view:id/search_input")
        
    # 如果没进到输入框页面，可能是刚才点偏了或者有弹窗遮挡
    if not search_input.exists(timeout=4):
        add_log("WARNING", "City search input not found, retrying click...")
        # 按一下物理返回键把挡住的东西退掉，然后再点一次
        d.press("back")
        time.sleep(1)
        if selector.exists():
            selector.click()
        else:
            add_log("ERROR", "City selector disappeared during retry; aborting.")
            return False
        time.sleep(2.5)
        
    # 重新查找输入框
    if d.app_current().get("package") != CTRIP_PACKAGE:
        add_log("ERROR", "Ctrip left the foreground during city selection; aborting.")
        return False

    search_input = d(packageName=CTRIP_PACKAGE, className="android.widget.EditText")
    if not search_input.exists():
        search_input = d(resourceId="ctrip.android.view:id/search_input")
        
    if search_input.exists():
        search_input.click() # 点进输入框唤起键盘
        add_log("INFO", f"Entering city: {city_name}")
        d.send_keys(city_name, clear=True) # 使用自动化键盘输入城市名
        time.sleep(3) # 等待网络请求搜索出相关的机场列表
        
        # Click suggestion (点击第一条联想出来的机场/城市结果)
        result_item = d(description="城市页第1条搜索结果")
        if not result_item.exists():
            result_item = d(className="android.widget.TextView", text=city_name)
        if not result_item.exists():
            result_item = d(className="android.widget.TextView", textContains=city_name)
            
        if result_item.exists(timeout=3):
            result_item.click() # 选中这个城市
            add_log("INFO", f"Selected city '{city_name}' from suggestions.")
            time.sleep(2)
            return True
        else:
            # 如果没出现联想列表，强行按回车键试试
            d.press("enter")
            add_log("INFO", f"Pressed Enter key to select city '{city_name}'")
            time.sleep(2)
            return True
    else:
        add_log("ERROR", "Failed to open city search input page.") # 失败了，记录日志
    return False

def choose_calendar_date_view(views, target_date, header_top, screen_width=BASE_SCREEN_WIDTH):
    """
    从日历层级中选择目标日号对应的可见节点。

    携程日历的实际行高会随版本、状态栏和滚动位置变化，不能只依赖
    固定坐标。用固定布局推算值只负责给候选节点排序，最终点击使用节点
    自己的 bounds 中心。
    """
    header_to_first_row = 84
    row_height = 178 * (screen_width / BASE_SCREEN_WIDTH)
    grid_left = 13 * (screen_width / BASE_SCREEN_WIDTH)
    grid_width = 1054 * (screen_width / BASE_SCREEN_WIDTH)
    col_width = grid_width / 7

    first_day_of_month = datetime(target_date.year, target_date.month, 1)
    first_col_idx = (first_day_of_month.weekday() + 1) % 7
    col_idx = (target_date.weekday() + 1) % 7
    week_idx = (target_date.day - 1 + first_col_idx) // 7
    expected_x = grid_left + (col_idx + 0.5) * col_width
    expected_y = header_top + header_to_first_row + week_idx * row_height + row_height / 2

    candidates = []
    target_day_text = str(target_date.day)
    for view in views:
        if view.get("text", "").strip() != target_day_text:
            continue
        if view.get("top", 0) < header_top:
            continue
        center_x = (view["left"] + view["right"]) / 2
        center_y = (view["top"] + view["bottom"]) / 2
        distance = (
            ((center_x - expected_x) / max(1, col_width)) ** 2
            + ((center_y - expected_y) / max(1, row_height)) ** 2
        )
        candidates.append((distance, view))

    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0])
    return candidates[0][1]


def selected_date_matches(d, target_date):
    """
    校验搜索页显示的日期；返回 None 表示当前版本没有暴露可识别日期文本。
    """
    try:
        views = collect_screen_views(d)
    except Exception as e:
        add_log("DEBUG", f"Failed to inspect selected date: {e}")
        return None

    date_pattern = re.compile(r"(?<!\d)(\d{1,2})\s*[-/.月]\s*(\d{1,2})(?:日)?")
    found_dates = []
    for view in views:
        match = date_pattern.search(view.get("text", ""))
        if match:
            found_dates.append((int(match.group(1)), int(match.group(2))))

    if not found_dates:
        return None
    return (target_date.month, target_date.day) in found_dates


def calendar_swipe_direction(target_date, visible_months):
    """
    根据当前日历可见月份决定搜索方向。

    携程日历向上滑通常进入更晚月份，向下滑回到更早月份。返回 None
    表示目标月份已经可见；没有可解析月份时沿用向上搜索作为 fallback。
    """
    target_key = (target_date.year, target_date.month)
    month_keys = sorted(set(visible_months))
    if target_key in month_keys:
        return None
    if not month_keys:
        return "up"
    if target_key < month_keys[0]:
        return "down"
    return "up"


def calendar_fallback_click_y(target_date, header_top, today=None, row_height=153, first_row_center_offset=135):
    """
    计算自绘日历的坐标 fallback。

    当前携程版本打开当月时会把“今天所在周”置于月份区域首行，
    而不是把每月 1 号置于首行。月份切换到未来月份后才从第 1 周开始。
    """
    today = today or datetime.now()
    first_day_of_month = datetime(target_date.year, target_date.month, 1)
    first_col_idx = (first_day_of_month.weekday() + 1) % 7
    target_week_idx = (target_date.day - 1 + first_col_idx) // 7

    if (target_date.year, target_date.month) == (today.year, today.month):
        current_week_idx = (today.day - 1 + first_col_idx) // 7
        visible_week_idx = max(0, target_week_idx - current_week_idx)
    else:
        visible_week_idx = target_week_idx

    return int(header_top + first_row_center_offset + visible_week_idx * row_height)


def select_date(d, date_str):
    """
    负责在携程自绘的日历控件上，精确点击指定的日期。
    由于携程日历不是原生的按钮组件，而是画在画布上的一整张图，所以必须算坐标点击。
    """
    try:
        ensure_screen_on(d)
        # 把字符串 "2026-09-26" 解析成 datetime 对象
        target_date = datetime.strptime(date_str, "%Y-%m-%d")
    except Exception as e:
        add_log("ERROR", f"Invalid date format: {date_str}. Use YYYY-MM-DD. Error: {e}")
        return False
        
    # 构造我们需要在屏幕上寻找的月份标题文字，比如 "2026年9月"
    target_header_text = f"{target_date.year}年{target_date.month}月"
    add_log("INFO", f"Opening calendar, looking for month header: {target_header_text}")
    
    # 寻找并点击主界面的“出发日期”入口，打开日历面板
    date_sel = d(description="depart date")
    if date_sel.exists(timeout=3):
        add_log("INFO", "Clicking date selector via description...")
        date_sel.click() # 点击打开日历
    else:
        add_log("ERROR", "Date selector not found; refusing unsafe coordinate fallback.")
        return False
    time.sleep(3) # 等待日历加载动画
    
    # 在日历面板里寻找目标月份的标题头 (例如"2026年9月")
    header_el = d(text=target_header_text)
    scroll_count = 0
    # 如果没看到目标月份，根据当前可见月份决定向前或向后滑动，最多 15 次
    while not header_el.exists() and scroll_count < 15:
        if d.app_current().get("package") != CTRIP_PACKAGE:
            add_log("ERROR", "Ctrip left the foreground while selecting a date; stopping all swipes.")
            return False
        ensure_screen_on(d)
        visible_months = []
        try:
            for view in collect_screen_views(d):
                match = re.fullmatch(r"(\d{4})年(\d{1,2})月", view.get("text", "").strip())
                if match:
                    visible_months.append((int(match.group(1)), int(match.group(2))))
        except Exception as e:
            add_log("DEBUG", f"Failed to read visible calendar months: {e}")

        direction = calendar_swipe_direction(target_date, visible_months)
        if direction is None:
            break
        add_log(
            "INFO",
            f"Header not visible. Swiping {direction} to search target month "
            f"(visible: {visible_months or 'unknown'})...",
        )
        d.swipe_ext(direction, scale=0.5)
        time.sleep(1) # 等待滑动动画结束
        scroll_count += 1
            
    if not header_el.exists():
        add_log("ERROR", f"Could not find target month header '{target_header_text}' after scroll.")
        return False
    
    # ================== 核心：坐标计算逻辑 ==================
    # 当前携程日历以周日为起点，日期文字行距约为 153 像素。
    # 左右边距和列宽仍沿用 UI hierarchy 测量值。
    try:
        screen_width, screen_height = d.window_size()
    except Exception:
        screen_width = d.info.get("displayWidth", BASE_SCREEN_WIDTH)
        screen_height = d.info.get("displayHeight", BASE_SCREEN_HEIGHT)
    scale_x = screen_width / BASE_SCREEN_WIDTH
    scale_y = screen_height / BASE_SCREEN_HEIGHT
    ROW_HEIGHT = 153 * scale_y # 当前自绘日历日期文字行距
    GRID_LEFT = 13 * scale_x # 左边距
    GRID_WIDTH = 1054 * scale_x # 总宽度
    COL_WIDTH = GRID_WIDTH / 7 # 每列宽度（周日到周六）
    
    # 算法：推算我们要找的日子在日历里的第几行、第几列
    first_day_of_month = datetime(target_date.year, target_date.month, 1) # 拿到这个月第一天
    first_col_idx = (first_day_of_month.weekday() + 1) % 7  # 算出第一天是星期几 (0=周日, 1=周一...星期几就是在第几列)
    col_idx = (target_date.weekday() + 1) % 7 # 算出我们的目标日期在第几列
    
    # 获取标题文本现在在屏幕上的 Y 坐标（这很重要，因为每次滑完它的位置都会变）
    bounds = header_el.info['bounds']
    header_top = bounds['top']
    add_log("INFO", f"Header '{target_header_text}' at Y={header_top}")
    
    # 计算固定坐标 fallback：标题顶部Y + 到第一行的距离 + (第几行 * 每行高度) + 半行高度
    click_y = calendar_fallback_click_y(
        target_date,
        header_top,
        today=datetime.now(),
        row_height=ROW_HEIGHT,
        first_row_center_offset=135 * scale_y,
    )
    # 计算固定坐标 fallback 的 X：左边距 + (第几列 + 0.5) * 列宽
    click_x = int(GRID_LEFT + (col_idx + 0.5) * COL_WIDTH)

    # 优先使用日历节点实际 bounds，避免固定行高偏移导致点到下一周。
    date_view = None
    try:
        date_view = choose_calendar_date_view(
            collect_screen_views(d),
            target_date,
            header_top,
            screen_width=screen_width,
        )
    except Exception as e:
        add_log("DEBUG", f"Failed to locate target date node; using coordinate fallback: {e}")

    if date_view:
        click_x = int((date_view["left"] + date_view["right"]) / 2)
        click_y = int((date_view["top"] + date_view["bottom"]) / 2)
        add_log(
            "INFO",
            f"Found date node for {date_str}; clicking its bounds center ({click_x}, {click_y}).",
        )
    else:
        add_log(
            "WARNING",
            f"Date node for {date_str} is not exposed; using coordinate fallback ({click_x}, {click_y}).",
        )
    
    # 异常处理：如果你要点的日期在这个月的月底（比如31号排在第6行），而现在屏幕下面没显示全（超出了手机屏幕高 2200）
    if click_y > screen_height - int(200 * scale_y):
        add_log("INFO", f"Target row Y={click_y} is off-screen. Scrolling up...")
        d.swipe_ext("up", scale=0.3) # 稍微往上滑一点点
        time.sleep(1)
        # 屏幕滑动后，原来所有的坐标都变了，必须重新算一遍标题当前的 Y 坐标
        if header_el.exists():
            bounds = header_el.info['bounds']
            header_top = bounds['top']
            click_y = calendar_fallback_click_y(
                target_date,
                header_top,
                today=datetime.now(),
                row_height=ROW_HEIGHT,
                first_row_center_offset=135 * scale_y,
            )
            add_log("INFO", f"After scroll: header at Y={header_top}, click_y={click_y}")
    
    # 算出坐标后，使用底层的坐标点击功能点下去
    add_log("INFO", f"Selecting date cell for {date_str} at coordinate ({click_x}, {click_y})")
    d.click(click_x, click_y)
    time.sleep(3) # 等待日历关闭
    
    # 验证一下日历是不是真的关了（看看主页的“查询”按钮有没有露出来）
    if d(text="查 询").exists(timeout=3) or d(textMatches="查.询").exists(timeout=1):
        add_log("INFO", "Calendar closed successfully after date selection.")
    else:
        # 如果没关掉（有时候点的是死角或者有弹窗卡住），强制按物理返回键把它关掉
        add_log("WARNING", "Calendar may not have closed. Pressing back...")
        d.press("back")
        time.sleep(2)

    selected_match = selected_date_matches(d, target_date)
    if selected_match is False:
        add_log(
            "ERROR",
            f"Selected date does not match requested date {date_str}; refusing to continue search.",
        )
        return False
    if selected_match is True:
        add_log("INFO", f"Verified selected date matches requested date {date_str}.")
    else:
        add_log("WARNING", f"Could not verify selected date text for {date_str}; continuing cautiously.")
    
    return True

def navigate_to_flights(d, dep, arr, date):
    """
    爬虫的核心主流程之一：负责从手机桌面一直操作到最终的“机票搜索结果列表页”
    """
    add_log("INFO", "Opening Ctrip App...")
    # 通过 App 的包名直接冷启动或唤醒携程
    start_ctrip_app(d)
    time.sleep(7) # 给 App 足够的启动时间加载主页
    ensure_screen_on(d)

    # 首次启动的服务协议必须由用户本人确认，自动化不代替用户接受法律条款。
    if d(text="同意并继续").exists(timeout=2):
        add_log(
            "ERROR",
            "携程首次启动协议尚未确认。请在模拟器中阅读并手动点击“同意并继续”，然后重新触发任务。",
        )
        return False
    
    # 尝试关掉一切可能弹出来的广告和提示框
    dismiss_ads(d)
    
    # 只处理 Android 权限控制器自己的按钮。不能在所有页面全局匹配
    # textContains="允许"，否则可能点击携程内容或跳进联系人等外部应用。
    current_package = d.app_current().get("package", "")
    if current_package in {
        "com.android.permissioncontroller",
        "com.google.android.permissioncontroller",
    }:
        permission_buttons = [
            d(resourceId="com.android.permissioncontroller:id/permission_allow_foreground_only_button"),
            d(resourceId="com.android.permissioncontroller:id/permission_allow_one_time_button"),
            d(resourceId="com.android.permissioncontroller:id/permission_allow_button"),
        ]
        for permission_button in permission_buttons:
            if permission_button.exists(timeout=0.5):
                add_log("INFO", "Granting the visible Android system permission...")
                permission_button.click()
                time.sleep(1)
                break
        
    # Manual Flights Page Automation (Primary path to guarantee date selection)
    add_log("INFO", "Using manual grid automation to guarantee correct date selection...")

    # 冷启动有时会恢复到上次中断的城市选择或日历子页。先退回机票查询页，
    # 避免把子页里的同名文字当成首页入口再次点击。
    already_on_flight_search = d(description="inquire main root").exists(timeout=1)
    for _ in range(3):
        if already_on_flight_search:
            break
        activity = d.app_current().get("activity", "")
        if "CityList" not in activity and "Calendar" not in activity:
            break
        add_log("INFO", f"Recovering from restored Ctrip subpage: {activity}")
        d.press("back")
        time.sleep(1.5)
        already_on_flight_search = d(description="inquire main root").exists(timeout=1)
    
    # 在主页上寻找“机票”入口图标
    flight_icon = d(description="机票")
    if not already_on_flight_search and not flight_icon.exists():
        flight_icon = d(text="机票")
        
    if already_on_flight_search or flight_icon.exists(timeout=3):
        ensure_screen_on(d)
        if not already_on_flight_search:
            add_log("INFO", "Clicking '机票' button...")
            flight_icon.click() # 点击进入机票搜索页
            time.sleep(4) # 等机票页加载
        else:
            add_log("INFO", "Already on flight search page; skipping duplicate entry click.")

        # 某些版本首次进入机票页会自动弹出目的地选择页。先关闭它，再由下面的
        # select_city 按既定顺序设置出发地和目的地。
        if "CityList" in d.app_current().get("activity", ""):
            add_log("INFO", "Closing automatically opened city picker before route entry...")
            d.press("back")
            time.sleep(2)
        
        # 2.0 Ensure '单程' (One Way) is selected to prevent 'Return Date' prompt
        # 确保当前是“单程”模式，否则选了去程日期后，系统会弹个日历逼你选返程日期，打乱我们的流程
        one_way = d(text="单程")
        if one_way.exists():
            try:
                if not one_way.info.get("selected", False):
                    add_log("INFO", "Selecting '单程' (One Way) mode...")
                    one_way.click()
                    time.sleep(1)
            except Exception as e:
                add_log("WARNING", f"One-way selector changed during page load; continuing safely: {e}")
        
        # 2a. Input Departure City (输入出发地)
        if not select_city(d, "depart city", dep):
            return False
        time.sleep(1.5)
        
        # 2b. Input Arrival City (输入目的地)
        if not select_city(d, "arrival city", arr):
            return False
        time.sleep(1.5)
        
        # 2c. Input Date (输入出发日期)
        if not select_date(d, date):
            return False
        
        # 2d. Click search button - check multiple selectors properly
        # NOTE: DO NOT use textContains='查询' - it matches '最近查询' instead!
        # 点击最下面的那个大的“查询”按钮。因为携程 UI 经常变，所以准备了很多种匹配规则
        inquire_clicked = False
        for selector_name, selector in [
            ("description='do inquire'", d(description="do inquire")),
            ("text='查 询'", d(text="查 询")),
            ("text='查询'", d(text="查询")),
            ("textMatches='查.询'", d(textMatches="查.询")),
            ("text='搜索'", d(text="搜索")),
        ]:
            if selector.exists(timeout=1):
                add_log("INFO", f"Clicking search button ({selector_name}) to fetch flight list...")
                selector.click() # 点击查询
                inquire_clicked = True
                break
        
        # 如果所有的规则都找不到那个查询按钮，直接暴力点屏幕最下方的固定坐标
        if not inquire_clicked:
            click_x, click_y = scaled_point(d, 540, 1234)
            add_log("INFO", f"Search button not found by selector. Clicking coordinate ({click_x}, {click_y})...")
            d.click(click_x, click_y)
            
        time.sleep(8)  # 国际航班的查询请求特别慢，留足 8 秒等它出结果
        return True
            
    return False

def parse_android_bounds(bounds_text):
    """
    Parse Android bounds strings like "[12,34][56,78]".
    """
    match = re.match(r'^\[(\d+),(\d+)\]\[(\d+),(\d+)\]$', bounds_text or "")
    if not match:
        return None
    left, top, right, bottom = [int(v) for v in match.groups()]
    return {"left": left, "top": top, "right": right, "bottom": bottom}

def collect_screen_views(d):
    """
    Fast text collection from a single UI hierarchy dump.

    Avoid iterating `for el in d()`: on complex Ctrip pages that can stall for
    minutes and keep the global device lock occupied.
    """
    views = []
    seen_view_keys = set()
    hierarchy = d.dump_hierarchy(compressed=False)
    root = ET.fromstring(hierarchy)

    for node in root.iter("node"):
        text = (node.attrib.get("text") or node.attrib.get("content-desc") or "").strip()
        if not text:
            continue
        bounds = parse_android_bounds(node.attrib.get("bounds"))
        if not bounds:
            continue

        view_key = (text, bounds["top"], bounds["bottom"], bounds["left"], bounds["right"])
        if view_key in seen_view_keys:
            continue
        seen_view_keys.add(view_key)

        views.append({
            "text": text,
            "top": bounds["top"],
            "bottom": bounds["bottom"],
            "left": bounds["left"],
            "right": bounds["right"],
            "y_center": (bounds["top"] + bounds["bottom"]) / 2,
        })

    return views

def parse_screen_flights(d, dep_date):
    """
    负责解析当前屏幕上显示的所有航班信息。
    这是整个爬虫里最复杂的部分：因为我们无法直接拿到底层数据，只能拿到屏幕上所有散落的可访问文字块。
    我们需要通过分析这些文字块的 Y 坐标，把属于同一个航班的文字拼成一行，然后再用正则提取价格、航司等。
    """
    try:
        views = collect_screen_views(d)
    except Exception as e:
        add_log("ERROR", f"Failed to dump/parse screen hierarchy: {e}")
        return []
            
    if not views:
        return []
        
    # Find '近期出发' or similar banners and exclude their Y-bands
    # 携程经常会在列表中间插播广告横幅，比如“近期出发”、“低价提醒”。这些里面的价格会干扰我们，必须剔除
    banner_y_centers = []
    for v in views:
        if v['text'] in ["近期出发", "低价提醒", "低价日历"]:
            banner_y_centers.append(v['y_center']) # 记录广告横幅所在的 Y 坐标位置
            
    # 识别底部导航栏的位置，如果有“推荐排序”或“价格低 → 高”，记录它的 Y 坐标，把在它下方或跟它重叠的文字全部剔除
    # 这能防止把半截卡片的文字或者底栏文字误认为是一个航班
    nav_bar_top = 99999
    for v in views:
        if v['text'] in ["推荐排序", "直飞优先", "价格低 → 高", "更多排序"]:
            nav_bar_top = min(nav_bar_top, v['top'])

    filtered_views = []
    for v in views:
        # If this view is within 150px of any banner, exclude it
        # 如果这个文本距离广告横幅上下 150 像素以内，就认为它是广告的一部分，扔掉
        in_banner = False
        for by in banner_y_centers:
            if abs(v['y_center'] - by) < 150:
                in_banner = True
                break
        
        # Also skip texts that are obviously from recommendation cards
        # 顺便过滤掉各种推荐卡片上的零碎文字
        if "省" in v['text'] or "起" in v['text'] or "周" in v['text'] and len(v['text']) <= 4:
            continue

        # 排除掉底部导航栏以及被导航栏遮挡的半截航班卡片。只要文本的底部超出了导航栏的顶部，就扔掉
        if v['bottom'] > nav_bar_top:
            continue
            
        if not in_banner:
            filtered_views.append(v)
            
    views = filtered_views # 覆盖为过滤干净后的文本列表
    
    if not views:
        return []
        
    # 把屏幕上的文本按照从上到下（Y中心点）排序
    views.sort(key=lambda x: x['y_center'])
    
    # ======== 关键算法：文本分组（聚类） ========
    # 我们把 Y 中心点非常接近（在 80 像素以内）的文本块，认为它们属于同一个航班条目
    rows = [] # 存放最终分好行的数组
    current_row = [] # 当前正在拼装的一行
    
    for v in views:
        if not current_row:
            current_row.append(v)
        else:
            prev_v = current_row[-1]
            # Tighten row grouping threshold from 120 to 80 to prevent merging adjacent rows
            # 如果当前文本的垂直高度跟上一个文本差不多（相差小于 80），说明它们是同一行的
            if abs(v['y_center'] - prev_v['y_center']) <= 80:
                current_row.append(v)
            else:
                # 如果差得比较多，说明已经换行了（到了下一个航班）
                rows.append(current_row)
                current_row = [v]
    if current_row:
        rows.append(current_row) # 把最后一行收尾加进去
        
    flights = [] # 最终提取出的航班结构化数据
    
    # 遍历刚才分好类的每一行（也就是每一个航班的方块区）
    for row in rows:
        texts = [v['text'] for v in row] # 把这一行里所有的文本摘出来
        row_str = " | ".join(texts) # 拼接成一个大长字符串方便做正则匹配
        
        # Match ticket price. Do not take the minimum number in the row:
        # Ctrip often shows discount labels like "已优惠 ¥100" below the real fare.
        price_found = extract_ticket_price(row)
                    
        # Match times: 08:00, 10:25
        # 提取起降时间：符合 XX:XX 格式的
        times = []
        for t in texts:
            if re.match(r'^\d{2}:\d{2}$', t):
                times.append(t)
                
        # Match flight number
        # 提取航班号：两个字母加一串数字，比如 MU5411
        flight_match = re.search(r'([A-Z0-9]{2}\d{3,4})', row_str)
        flight_no = flight_match.group(1) if flight_match else ""
        
        # Match airline
        # 提取航空公司名字：靠关键词穷举去猜
        airline = "未知航空"
        airlines_keywords = ["东方", "南方", "国际", "海南", "吉祥", "春秋", "厦门", "山东", "深圳", "四川", "上海", "联合", "九元", "西藏", "青岛", "捷星", "乐桃", "全日空", "日本", "国泰", "大韩", "韩亚"]
        for t in texts:
            for k in airlines_keywords:
                if k in t and len(t) < 12:
                    airline = t
                    break
            if airline != "未知航空":
                break
                
        # Match transfer status and transit visa
        # 提取中转情况和过境签证要求
        is_transfer = 0
        transit_visa = "不需要"
        for t in texts:
            # 如果文本里包含“中转”、“不同机场”等字眼，说明这不是直飞
            if any(k in t for k in ["中转", "不同机场", "同城转", "转机", "经停"]):
                is_transfer = 1
            if t.strip() == "转" or re.match(r'^转\s+\S+$', t.strip()):
                is_transfer = 1
            # 如果文本里说过境签，记下来提醒用户
            if any(k in t for k in ["过境签", "过境签证", "需过境"]):
                transit_visa = t.strip()

        # If we have a price and departure/arrival times, it's a valid row
        # 校验合法性：只有当一行里同时有价格，且至少有起降 2 个时间点时，才认为它是一条合法的航班数据
        if price_found is not None and len(times) >= 2:
            price = float(price_found)
            dep_t = times[0]
            arr_t = times[1]
            
            # Synthesize flight number if empty
            # 万一没抓到航班号，用航司和时间人工捏造一个临时 ID
            if not flight_no:
                airline_code = "".join([c for c in airline if c.isalpha()])[:3]
                flight_no = f"{airline_code or 'FL'}_{dep_t.replace(':', '')}"
                
            # Calculate bounds
            # 算出这一个航班卡片在屏幕上的绝对边界（为了等会儿截图算裁剪框用）
            row_top = min(v['top'] for v in row)
            row_bottom = max(v['bottom'] for v in row)
            row_left = min(v['left'] for v in row)
            row_right = max(v['right'] for v in row)
                
            # 组装这架航班的字典数据，加入到最终结果列表里
            flights.append({
                "flight_number": flight_no,
                "airline": airline,
                "departure_time": f"{dep_date} {dep_t}" if dep_t else "",
                "arrival_time": f"{dep_date} {arr_t}" if arr_t else "",
                "price": price,
                "is_transfer": is_transfer,
                "transit_visa": transit_visa,
                "bounds": {"top": row_top, "bottom": row_bottom, "left": row_left, "right": row_right}
            })
            
    return flights

def extract_ticket_price(row):
    """
    Extract the actual ticket fare from one visual flight row.

    The row can also contain coupon/discount amounts such as "已优惠 ¥100".
    Those are usually right-aligned too, so choosing the minimum numeric value is
    wrong. Prefer the main fare: right-side price text, containing ¥, larger
    text bounds, and not attached to discount keywords.
    """
    row_left = min(v['left'] for v in row)
    row_right = max(v['right'] for v in row)
    row_width = max(1, row_right - row_left)
    right_column_start = row_left + row_width * 0.58
    discount_keywords = ["优惠", "省", "减", "券", "红包", "返", "立减", "折扣"]
    row_has_discount_text = any(
        any(k in v['text'] for k in discount_keywords)
        for v in row
    )
    candidates = []

    for v in row:
        text = v['text'].replace(",", "").strip()
        if not text:
            continue

        # Prefer explicit fare-looking text. Keep plain numbers as fallback for
        # app variants that split "¥" and the number into separate TextViews.
        if "¥" in text:
            matches = re.findall(r'¥\s*(\d{3,5})', text)
        elif text.isdigit():
            matches = [text]
        else:
            matches = []

        for match in matches:
            val = int(match)
            if val < 100 or val >= 20000:
                continue

            height = max(1, v['bottom'] - v['top'])
            is_right_side = v['right'] >= right_column_start or v['left'] >= right_column_start
            has_discount_text = any(k in text for k in discount_keywords)

            # Discount labels are useful context but should not beat the fare.
            if has_discount_text or (row_has_discount_text and val <= 500):
                score = -1000
            else:
                score = 0
                if "¥" in text:
                    score += 120
                if is_right_side:
                    score += 80
                score += height * 3
                # The main fare is normally above discount/availability tags.
                score -= v['top'] * 0.02

            candidates.append({
                "value": val,
                "score": score,
                "height": height,
                "top": v['top'],
                "right": v['right'],
            })

    if not candidates:
        return None

    candidates.sort(key=lambda c: (c["score"], c["height"], -c["top"], c["right"]), reverse=True)
    if candidates[0]["score"] < 0:
        return None
    return candidates[0]["value"]

def flight_matches(candidate, target):
    """
    判断当前屏幕解析到的航班是否是本次查询选出的最低价航班。

    航班号有时由页面解析临时生成，因此同时使用价格和起飞时间约束，
    避免仅凭价格误点同价的另一趟航班。
    """
    return (
        candidate.get("flight_number") == target.get("flight_number")
        and candidate.get("price") == target.get("price")
        and candidate.get("departure_time") == target.get("departure_time")
    )

def find_and_click_flight(d, target_flight, dep_date, max_upward_swipes):
    """
    从抓取结束时的列表位置开始，逐屏向上寻找并点击目标航班。
    """
    for attempt in range(max_upward_swipes + 1):
        ensure_screen_on(d)
        screen_flights = parse_screen_flights(d, dep_date)
        matched = next(
            (flight for flight in screen_flights if flight_matches(flight, target_flight)),
            None,
        )
        if matched:
            bounds = matched.get("bounds")
            if not bounds:
                add_log("WARNING", "Lowest-price flight was found but has no clickable bounds.")
                return False

            click_x = int((bounds["left"] + bounds["right"]) / 2)
            click_y = int((bounds["top"] + bounds["bottom"]) / 2)
            add_log(
                "INFO",
                f"Clicking lowest-price flight {target_flight['flight_number']} "
                f"(¥{target_flight['price']}) at ({click_x}, {click_y})...",
            )
            d.click(click_x, click_y)
            return True

        if attempt < max_upward_swipes:
            add_log(
                "DEBUG",
                f"Lowest-price flight not visible yet; scrolling toward list top "
                f"({attempt + 1}/{max_upward_swipes})...",
            )
            d.swipe_ext("down", scale=0.7)
            time.sleep(2)

    add_log(
        "WARNING",
        f"Could not relocate lowest-price flight {target_flight['flight_number']} "
        f"(¥{target_flight['price']}); skipping detail screenshot.",
    )
    return False

def flight_detail_page_visible(d):
    """
    识别用户指定的航班舱位/价格选择页。
    """
    views = collect_screen_views(d)
    texts = [view["text"] for view in views]
    has_cabin_section = any(
        any(marker in text for marker in ["经济舱", "公务舱", "头等舱"])
        for text in texts
    )
    has_purchase_action = any(
        text.strip() == "订" or "选购" in text
        for text in texts
    )
    return has_cabin_section and has_purchase_action

def wait_for_flight_detail_page(d, timeout=15, poll_interval=1):
    """
    等待目标页完成加载，避免把加载动画或中间页保存成目标截图。
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        ensure_screen_on(d)
        try:
            if flight_detail_page_visible(d):
                return True
        except Exception as e:
            add_log("DEBUG", f"Failed to inspect flight detail page while loading: {e}")
        time.sleep(poll_interval)
    return False

def save_flight_detail_screenshot(d, flight, screenshot_dir=None):
    """
    保存目标详情页全屏截图，并返回可写入数据库的静态资源路径。
    """
    if screenshot_dir is None:
        screenshot_dir = GENERATED_SCREENSHOT_DIR
    os.makedirs(screenshot_dir, exist_ok=True)

    safe_flight_number = re.sub(r"[^A-Za-z0-9_-]", "_", flight["flight_number"])
    target_filename = f"target_{safe_flight_number}_{int(time.time())}.png"
    target_path = os.path.join(screenshot_dir, target_filename)
    ensure_screen_on(d)
    d.screenshot().save(target_path)
    add_log("DEBUG", f"Lowest-price flight detail screenshot saved to {target_path}")
    return f"/static/generated/{target_filename}"

def return_to_flight_list_after_detail_failure(d):
    """
    详情页处理失败后尽量返回航班列表；恢复失败只记日志，不丢弃已抓取结果。
    """
    try:
        d.press("back")
        time.sleep(2)
        add_log("INFO", "Returned to flight list after detail screenshot failure.")
    except Exception as e:
        add_log("WARNING", f"Failed to return to flight list after detail screenshot failure: {e}")

def capture_lowest_flight_detail(
    d,
    flights,
    dep_date,
    target_price,
    max_upward_swipes,
    screenshot_dir=None,
):
    """
    达标时只进入完整查询结果中的最低价航班，并保存目标页全屏截图。
    """
    if not flights or target_price is None:
        return False

    lowest_flight = min(flights, key=lambda flight: flight["price"])
    if lowest_flight["price"] > target_price:
        return False

    add_log(
        "INFO",
        f"Lowest price meets target: {lowest_flight['flight_number']} "
        f"¥{lowest_flight['price']} <= ¥{target_price}. Opening flight detail page...",
    )
    if not find_and_click_flight(d, lowest_flight, dep_date, max_upward_swipes):
        return False

    try:
        if not wait_for_flight_detail_page(d):
            add_log(
                "WARNING",
                "Flight detail page did not load before timeout; skipping target screenshot.",
            )
            return_to_flight_list_after_detail_failure(d)
            return False

        lowest_flight["screenshot_path"] = save_flight_detail_screenshot(
            d,
            lowest_flight,
            screenshot_dir=screenshot_dir,
        )
        add_log(
            "INFO",
            f"Captured full-screen detail image for lowest-price flight "
            f"{lowest_flight['flight_number']}.",
        )
        return True
    except Exception as e:
        add_log("ERROR", f"Failed to capture lowest-price flight detail screenshot: {e}")
        return_to_flight_list_after_detail_failure(d)
        return False

def scrape_ctrip_mobile(dep_city, arr_city, dep_date, target_price=None, route_id=None):
    """
    整个手机爬虫的最上层总控函数。它会调用前面写好的所有函数，把整个流程串起来。
    """
    # 1. 尝试连接插在电脑上的手机
    d = init_device()
    if not d:
        return []
        
    try:
        configure_screen_awake(d)
        # 2. 如果手机黑屏了，解锁手机
        unlock_device(d)
        
        # 3. 操控手机打开携程，填地点、挑日期、点搜索，最后停留在航班列表页
        success = navigate_to_flights(d, dep_city, arr_city, dep_date)
        if not success:
            add_log("WARNING", "Failed to navigate to flight list results.")
            # 导航失败时绝不能继续执行下面的固定滑屏循环，否则当前页面如果是
            # 开屏广告或促销页，爬虫会把广告页当成航班列表持续滑动。
            d.app_stop(CTRIP_PACKAGE)
            return []
            
        all_flights = [] # 存放滑动抓取到的所有航班
        seen_keys = set() # 用来给航班去重（因为滑动屏幕时，上下两页会有重复重叠的航班）
        last_screen_index = 0
        
        time.sleep(4) # 等待列表第一页的机票数据完全加载出来
        
        # 4. 循环滑屏抓取：连滑 4 页屏幕（一般能覆盖全天最便宜的十几趟航班了）
        for screen in range(4):
            ensure_screen_on(d)
            add_log("INFO", f"Scraping screen page {screen + 1}...")
            # 解析当前这一屏上能看见的所有航班
            screen_flights = parse_screen_flights(d, dep_date)

            # 航班列表页至少应该能解析出一条航班。解析结果为空通常意味着
            # 查询没有成功、页面被弹窗覆盖，或已经误入广告页。此时停止操作，
            # 避免在未知页面继续盲目滑动。
            if not screen_flights:
                add_log(
                    "WARNING",
                    f"No flights found on screen page {screen + 1}; stopping to avoid swiping an unexpected page.",
                )
                break
            last_screen_index = screen
            
            new_count = 0
            for f in screen_flights:
                # 把“航班号 + 价格”作为唯一标识去重
                key = (f["flight_number"], f["price"])
                if key not in seen_keys:
                    seen_keys.add(key)
                    all_flights.append(f)
                    new_count += 1
                    
            add_log("INFO", f"Found {len(screen_flights)} flights on screen, {new_count} were new.")
            
            # 6. 不管达不达标，只要是第一页，都保存一张全图给网页控制台展示用
            if screen == 0:
                ensure_screen_on(d)
                screenshot_dir = GENERATED_SCREENSHOT_DIR
                os.makedirs(screenshot_dir, exist_ok=True)
                route_screenshot_path = None
                if route_id is not None:
                    route_screenshot_path = os.path.join(screenshot_dir, f"screenshot_route_{route_id}.png")

                img = d.screenshot()
                if route_screenshot_path:
                    img.save(route_screenshot_path)
                    add_log("DEBUG", f"Route screenshot saved to {route_screenshot_path}")

                # Keep the legacy global screenshot for older pages or quick debugging.
                screenshot_path = os.path.join(screenshot_dir, "screenshot.png")
                img.save(screenshot_path)
                add_log("DEBUG", f"Screenshot saved to {screenshot_path}")
                
            # 7. 当前这一屏幕抓完后再翻到下一页；最后一屏无需继续滑动。
            if screen < 3:
                ensure_screen_on(d)
                add_log("INFO", "Scrolling down flight list...")
                d.swipe_ext("up", scale=0.6)
                time.sleep(2.5) # 给列表滑动滚动留出时间
            
        # 8. 抓取结束，按照价格从便宜到贵排个序
        all_flights.sort(key=lambda x: x["price"])
        add_log("INFO", f"Mobile crawling completed. Total unique flights extracted: {len(all_flights)}")

        # 9. 完整列表抓取后，只有全局最低价达到目标价时才进入详情页。
        # last_screen_index 表示当前最多需要向列表顶部恢复多少屏。
        capture_lowest_flight_detail(
            d,
            all_flights,
            dep_date,
            target_price,
            max_upward_swipes=last_screen_index + 1,
        )
        
        # 10. 任务圆满完成，优雅地杀掉携程 App，把手机恢复桌面状态
        d.app_stop(CTRIP_PACKAGE)
        return all_flights
        
    except Exception as e:
        # 万一代码抛错崩溃，记录日志并强行截个图留存犯罪现场
        add_log("ERROR", f"Exception in mobile crawl: {e}")
        try:
            screenshot_dir = GENERATED_SCREENSHOT_DIR
            os.makedirs(screenshot_dir, exist_ok=True)
            img = d.screenshot()
            if route_id is not None:
                img.save(os.path.join(screenshot_dir, f"screenshot_route_{route_id}.png"))
            img.save(os.path.join(screenshot_dir, "screenshot.png"))
        except Exception:
            pass
        return []

# 下方代码是用来单独测试这个爬虫脚本用的，不会在正式运行的 Web 服务中被触发
if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 4:
        dep = sys.argv[1]
        arr = sys.argv[2]
        date = sys.argv[3]
        results = scrape_ctrip_mobile(dep, arr, date)
        print("\nScraped Flights:")
        for r in results[:10]:
            print(f"- {r['airline']} {r['flight_number']}: {r['departure_time']} -> {r['arrival_time']} | ¥{r['price']}")
    else:
        print("Usage: python mobile_crawler.py <dep> <arr> <date>")
        # 默认演示用测试路线
        results = scrape_ctrip_mobile("上海", "广州", "2026-06-25")
        print(f"Test run found {len(results)} flights.")
