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

def init_device():
    """
    初始化连接安卓设备。
    它会自动寻找插在 USB 上或者同一 WiFi 局域网下的手机，并在手机端安装必要的服务。
    """
    try:
        add_log("INFO", "Connecting to Android device...")
        d = u2.connect() # 调用 uiautomator2 进行连接
        add_log("INFO", f"Connected successfully. Device: {d.device_info}") # 打印手机设备信息
        return d
    except Exception as e:
        add_log("ERROR", f"Failed to connect to device. Error: {e}") # 记录连接失败错误
        return None

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

        try:
            d.unlock()
        except Exception:
            pass

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

def select_city(d, desc_selector, city_name):
    """
    负责在携程的主页面点击城市选择框，输入城市名，并在搜索结果里点击这个城市
    :param d: uiautomator2 对象
    :param desc_selector: 出发地或目的地框的内容描述 (content-desc)
    :param city_name: 要输入的城市名字，比如 "成都"
    """
    ensure_screen_on(d)
    selector = d(description=desc_selector) # 寻找出发地/目的地按钮
    if selector.exists(timeout=6):
        add_log("INFO", f"Clicking city selector '{desc_selector}' via description...")
        selector.click() # 点击它，进入城市搜索页面
    else:
        # 如果 UI 更新导致找不到该描述，使用备用坐标点击（硬编码点击位置）
        if desc_selector == "depart city":
            click_x, click_y = 256, 398 # 粗略的出发地中心点坐标
        else:
            click_x, click_y = 744, 398 # 粗略的目的地中心点坐标
        add_log("INFO", f"City selector '{desc_selector}' not found. Clicking coordinate ({click_x}, {click_y})...")
        d.click(click_x, click_y)
        
    time.sleep(2.5) # 给页面滑出动画一点时间
    
    # 验证是否成功进到了城市搜索页面，寻找输入框
    search_input = d(className="android.widget.EditText")
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
            d.click(click_x, click_y)
        time.sleep(2.5)
        
    # 重新查找输入框
    search_input = d(className="android.widget.EditText")
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
        # 如果找不到入口，用写死的固定坐标去点
        add_log("INFO", "Date selector description not found. Clicking coordinate (500, 552)...")
        d.click(500, 552)
    time.sleep(3) # 等待日历加载动画
    
    # 在日历面板里寻找目标月份的标题头 (例如"2026年9月")
    header_el = d(text=target_header_text)
    scroll_count = 0
    # 如果没看到目标月份，就不停往上滑屏幕，最多滑 15 次 (找一年以内的机票)
    while not header_el.exists() and scroll_count < 15:
        ensure_screen_on(d)
        add_log("INFO", "Header not visible. Swiping up to search...")
        d.swipe_ext("up", scale=0.5) # 滑动半个屏幕
        time.sleep(1) # 等待滑动动画结束
        scroll_count += 1
            
    if not header_el.exists():
        add_log("ERROR", f"Could not find target month header '{target_header_text}' after scroll.")
        return False
    
    # ================== 核心：坐标计算逻辑 ==================
    # Calendar layout measurements (from UI hierarchy analysis):
    # 携程日历的排版规律：
    # - 它是以周日为起点的：日一二三四五六
    # - 从“2026年X月”这个标题文本的顶部往下数，第 84 个像素，就是第一行日期所在位置
    # - 每一行日期控件的高度是 178 像素
    # - 日历的左右边距：左起 13，总宽 1054（除以 7 等于每列的宽度）
    HEADER_TO_FIRST_ROW = 84  # pixels from header text top to first week row top
    ROW_HEIGHT = 178 # 每行高度
    GRID_LEFT = 13 # 左边距
    GRID_WIDTH = 1054 # 总宽度
    COL_WIDTH = GRID_WIDTH / 7 # 每列宽度（周日到周六）
    
    # 算法：推算我们要找的日子在日历里的第几行、第几列
    first_day_of_month = datetime(target_date.year, target_date.month, 1) # 拿到这个月第一天
    first_col_idx = (first_day_of_month.weekday() + 1) % 7  # 算出第一天是星期几 (0=周日, 1=周一...星期几就是在第几列)
    col_idx = (target_date.weekday() + 1) % 7 # 算出我们的目标日期在第几列
    week_idx = (target_date.day - 1 + first_col_idx) // 7 # 算出目标日期在这个月排在第几行（0是第一行）
    
    # 获取标题文本现在在屏幕上的 Y 坐标（这很重要，因为每次滑完它的位置都会变）
    bounds = header_el.info['bounds']
    header_top = bounds['top']
    add_log("INFO", f"Header '{target_header_text}' at Y={header_top}")
    
    # 计算精确的屏幕点击 Y 坐标：标题顶部Y + 到第一行的距离 + (第几行 * 每行高度) + 半行高度（点在中心）
    first_row_top = header_top + HEADER_TO_FIRST_ROW
    click_y = int(first_row_top + week_idx * ROW_HEIGHT + ROW_HEIGHT / 2)
    # 计算精确的屏幕点击 X 坐标：左边距 + (第几列 + 0.5) * 列宽
    click_x = int(GRID_LEFT + (col_idx + 0.5) * COL_WIDTH)
    
    # 异常处理：如果你要点的日期在这个月的月底（比如31号排在第6行），而现在屏幕下面没显示全（超出了手机屏幕高 2200）
    if click_y > 2200:
        add_log("INFO", f"Target row Y={click_y} is off-screen. Scrolling up...")
        d.swipe_ext("up", scale=0.3) # 稍微往上滑一点点
        time.sleep(1)
        # 屏幕滑动后，原来所有的坐标都变了，必须重新算一遍标题当前的 Y 坐标
        if header_el.exists():
            bounds = header_el.info['bounds']
            header_top = bounds['top']
            first_row_top = header_top + HEADER_TO_FIRST_ROW
            click_y = int(first_row_top + week_idx * ROW_HEIGHT + ROW_HEIGHT / 2)
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
    
    return True

def navigate_to_flights(d, dep, arr, date):
    """
    爬虫的核心主流程之一：负责从手机桌面一直操作到最终的“机票搜索结果列表页”
    """
    add_log("INFO", "Opening Ctrip App...")
    # 通过 App 的包名直接冷启动或唤醒携程
    d.app_start("ctrip.android.view", stop=True)
    time.sleep(7) # 给 App 足够的启动时间加载主页
    ensure_screen_on(d)
    
    # 尝试关掉一切可能弹出来的广告和提示框
    dismiss_ads(d)
    
    # Dismiss potential system dialogs (关掉手机系统级别的弹窗，比如“携程请求获取地理位置”)
    if d(textContains="允许").exists(timeout=1):
        d(textContains="允许").click()
        time.sleep(1)
        
    # Manual Flights Page Automation (Primary path to guarantee date selection)
    add_log("INFO", "Using manual grid automation to guarantee correct date selection...")
    
    # 在主页上寻找“机票”入口图标
    flight_icon = d(description="机票")
    if not flight_icon.exists():
        flight_icon = d(text="机票")
        
    if flight_icon.exists(timeout=3):
        ensure_screen_on(d)
        add_log("INFO", "Clicking '机票' button...")
        flight_icon.click() # 点击进入机票搜索页
        time.sleep(4) # 等机票页加载
        
        # 2.0 Ensure '单程' (One Way) is selected to prevent 'Return Date' prompt
        # 确保当前是“单程”模式，否则选了去程日期后，系统会弹个日历逼你选返程日期，打乱我们的流程
        one_way = d(text="单程")
        if one_way.exists:
            add_log("INFO", "Selecting '单程' (One Way) mode...")
            one_way.click()
            time.sleep(1)
        
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
            add_log("INFO", "Search button not found by selector. Clicking coordinate (540, 1234)...")
            d.click(540, 1234)
            
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
            
        all_flights = [] # 存放滑动抓取到的所有航班
        seen_keys = set() # 用来给航班去重（因为滑动屏幕时，上下两页会有重复重叠的航班）
        
        time.sleep(4) # 等待列表第一页的机票数据完全加载出来
        
        # 4. 循环滑屏抓取：连滑 4 页屏幕（一般能覆盖全天最便宜的十几趟航班了）
        for screen in range(4):
            ensure_screen_on(d)
            add_log("INFO", f"Scraping screen page {screen + 1}...")
            # 解析当前这一屏上能看见的所有航班
            screen_flights = parse_screen_flights(d, dep_date)
            
            new_count = 0
            for f in screen_flights:
                # 把“航班号 + 价格”作为唯一标识去重
                key = (f["flight_number"], f["price"])
                if key not in seen_keys:
                    seen_keys.add(key)
                    
                    # 5. 如果我们在执行降价监控，并且当前这个航班跌破了用户的心理底价
                    if target_price and f["price"] <= target_price:
                        add_log("INFO", f"Target price met! Capturing screenshot for {f['flight_number']}...")
                        # 准备截图保存目录
                        screenshot_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
                        os.makedirs(screenshot_dir, exist_ok=True)
                        target_filename = f"target_{f['flight_number']}_{int(time.time())}.png"
                        target_path = os.path.join(screenshot_dir, target_filename)
                        
                        try:
                            # 截取一整张全屏图
                            img = d.screenshot()
                            bounds = f.get("bounds")
                            if bounds:
                                # 把达标的那个航班卡片所在的区域“裁剪”出来（向外扩大20个像素边界）
                                padding = 20
                                box = (
                                    max(0, bounds["left"] - padding),
                                    max(0, bounds["top"] - padding),
                                    min(img.width, bounds["right"] + padding),
                                    min(img.height, bounds["bottom"] + padding)
                                )
                                cropped_img = img.crop(box)
                                cropped_img.save(target_path) # 保存被裁剪的小截图
                            else:
                                img.save(target_path) # 如果没算对边界，就老老实实保存全屏图
                            # 把截图路径写进航班数据里，后面发微信推送就能带上图
                            f["screenshot_path"] = f"/static/{target_filename}"
                            add_log("DEBUG", f"Target screenshot saved to {target_path}")
                        except Exception as e:
                            add_log("ERROR", f"Failed to save target screenshot: {e}")
                    
                    all_flights.append(f)
                    new_count += 1
                    
            add_log("INFO", f"Found {len(screen_flights)} flights on screen, {new_count} were new.")
            
            # 6. 不管达不达标，只要是第一页，都保存一张全图给网页控制台展示用
            if screen == 0:
                ensure_screen_on(d)
                screenshot_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
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
                
            # 7. 当前这一屏幕抓完了，手指向上滑动，翻到下一页
            ensure_screen_on(d)
            add_log("INFO", "Scrolling down flight list...")
            d.swipe_ext("up", scale=0.6)
            time.sleep(2.5) # 给列表滑动滚动留出时间
            
        # 8. 抓取结束，按照价格从便宜到贵排个序
        all_flights.sort(key=lambda x: x["price"])
        add_log("INFO", f"Mobile crawling completed. Total unique flights extracted: {len(all_flights)}")
        
        # 9. 任务圆满完成，优雅地杀掉携程 App，把手机恢复桌面状态
        d.app_stop("ctrip.android.view")
        return all_flights
        
    except Exception as e:
        # 万一代码抛错崩溃，记录日志并强行截个图留存犯罪现场
        add_log("ERROR", f"Exception in mobile crawl: {e}")
        try:
            screenshot_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
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
