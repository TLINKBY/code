import threading # 导入线程模块，用于创建锁和后台线程
from datetime import datetime # 导入时间模块
from apscheduler.schedulers.background import BackgroundScheduler # 导入后台任务调度器
from apscheduler.triggers.interval import IntervalTrigger # 导入间隔触发器（例如每30分钟执行一次）
from db import get_active_routes, get_route, add_price_log, add_log # 导入数据库操作函数
from mobile_crawler import scrape_ctrip_mobile # 导入核心的手机自动抓取爬虫函数
from notifier import send_wechat_notification # 导入消息推送提醒函数

# 初始化后台调度器，它会在后台独立运行，不会阻塞主程序
scheduler = BackgroundScheduler()
scheduler.start() # 启动调度器

# 全局设备锁：非常关键！因为所有任务都在争抢同一个手机屏幕（uiautomator2）
# 如果不加锁，两个任务同时运行会让手机乱点。加锁后，新任务会乖乖排队等待
device_lock = threading.Lock()

def run_crawl_job(route_id):
    """
    具体的监控爬虫任务函数，根据传入的 route_id（路线ID）执行抓取
    """
    # 从数据库获取最新的路线配置
    route = get_route(route_id)
    # 如果路线不存在，或者用户已经在网页上关掉了这个任务
    if not route or not route["is_active"]:
        add_log("INFO", f"路线 ID {route_id} 已停用，跳过执行。") # 记录日志
        remove_route_job(route_id) # 从调度器中彻底移除这个任务
        return
        
    add_log("INFO", f"路线 ID {route_id} 正在等待获取手机控制权(全局锁)...")
    
    # 阻塞并等待获取全局锁。只有拿到锁，才能开始操控手机
    with device_lock:
        try:
            # 拿到锁后，再次检查路线状态（因为排队等待期间，用户可能已经修改或关闭了任务）
            route = get_route(route_id)
            if not route or not route["is_active"]:
                add_log("INFO", f"路线 ID {route_id} 在排队期间被停用，取消执行。")
                remove_route_job(route_id)
                return
                
            # 提取路线的详细信息
            dep = route["departure"] # 出发地
            arr = route["arrival"] # 目的地
            date = route["date"] # 出发日期
            target = route["target_price"] # 用户设定的目标心理价位
            
            add_log("INFO", f"开始执行手机自动化查询：{dep} -> {arr} 日期：{date}")
            
            # 调用手机爬虫，它会操控手机打开携程并返回屏幕上识别到的所有航班列表
            # 传入 target_price 是为了在发现低价时立刻在手机上截个图
            flights = scrape_ctrip_mobile(dep, arr, date, target_price=target, route_id=route_id)
            
            # 如果爬虫没有返回任何数据（可能是网络卡顿、UI变化、没搜到结果）
            if not flights:
                add_log("WARNING", f"本次未获取到 {dep} -> {arr} ({date}) 的航班数据")
                return
                
            # flights 列表在爬虫里已经按价格从低到高排序了，所以第一个就是最便宜的
            lowest_flight = flights[0] 
            lowest_price = lowest_flight["price"] # 获取当前最低价
            
            add_log("INFO", f"手机端查到的最低价: ¥{lowest_price} ({lowest_flight['airline']} {lowest_flight['flight_number']})")
            
            # 遍历抓取到的所有航班，把它们的价格记录存进数据库
            # 这样前端网页上就能画出价格走势图
            for f in flights:
                add_price_log(
                    route_id=route_id,
                    flight_number=f["flight_number"],
                    airline=f["airline"],
                    departure_time=f["departure_time"],
                    arrival_time=f["arrival_time"],
                    price=f["price"],
                    is_transfer=f.get("is_transfer", 0),
                    transit_visa=f.get("transit_visa", "不需要"),
                    screenshot_path=f.get("screenshot_path") # 如果有截图，保存截图路径
                )
                
            # 降价判定逻辑：如果你设置了目标价，并且当前的最低价 <= 你的目标价
            if target and lowest_price <= target:
                # 构造推送通知的标题
                title = f"✈️ 机票降价提醒: {dep} ➔ {arr} (¥{lowest_price})"
                # 构造推送通知的具体内容（Markdown 格式）
                content = (
                    f"### 机票监控提醒\n\n"
                    f"您监控的手机App航线有价格变动，当前价格已低于您的预期！\n\n"
                    f"- **航线**: {dep} ➔ {arr}\n"
                    f"- **出发日期**: {date}\n"
                    f"- **当前最低价**: **¥{lowest_price}**\n"
                    f"- **您的目标价**: ¥{target}\n"
                    f"- **最低航班**: {lowest_flight['airline']} {lowest_flight['flight_number']}\n"
                    f"- **起飞时间**: {lowest_flight['departure_time']}\n\n"
                )
                
                # 如果爬虫拍了截图，在通知里加上截图的提示
                screenshot_path = lowest_flight.get("screenshot_path")
                if screenshot_path:
                    content += f"📸 **已自动截图**, 图像保存在项目目录: {screenshot_path}\n\n"
                    
                content += "请尽快前往携程 App 进行预订！"
                # 调用通知模块发送 Bark/微信 提醒
                send_wechat_notification(title, content)
                
        # 捕获整个过程中可能发生的任何崩溃错误，防止程序死掉
        except Exception as e:
            add_log("ERROR", f"路线 ID {route_id} 执行出错: {str(e)}")

def get_job_id(route_id):
    """
    生成一个任务的唯一ID，方便在调度器里查找或删除它
    """
    return f"route_job_{route_id}"

def add_route_job(route):
    """
    把一条路线加入到定时任务调度器中
    """
    route_id = route["id"]
    job_id = get_job_id(route_id) # 获取唯一任务ID
    interval = route["interval_minutes"] # 获取检查间隔（分钟）
    
    # 为了防止重复添加，先尝试删除可能已经存在的同名旧任务
    remove_route_job(route_id)
    
    # 往调度器里添加一个新任务，按照指定的分钟数循环执行
    # 注意：我们设置 next_run_time=datetime.now() 这样可以让任务在添加后立马执行第一次，不用先干等 15 分钟
    scheduler.add_job(
        func=run_crawl_job, # 要执行的函数
        trigger=IntervalTrigger(minutes=interval), # 触发器：每隔 interval 分钟触发一次
        args=[route_id], # 传给函数的参数
        id=job_id, # 任务唯一ID
        name=f"Crawl {route['departure']}->{route['arrival']}", # 任务名字（给人看的）
        replace_existing=True, # 允许替换已存在的任务
        next_run_time=datetime.now() # 立马执行第一次
    )
    add_log("INFO", f"已启动监控任务：路线 ID {route_id}，每 {interval} 分钟检查一次。")

def remove_route_job(route_id):
    """
    从调度器中删除某条路线的定时任务（比如你关闭了监控开关）
    """
    job_id = get_job_id(route_id)
    # 检查调度器里有没有这个任务，有的话就移除
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
        add_log("INFO", f"已停止监控任务：路线 ID {route_id}。")

def trigger_route_now_async(route_id):
    """
    用户手动点击“立即执行”时调用的函数。它会新开一个后台线程立马去执行一次查询
    """
    # 创建一个后台线程去跑 run_crawl_job
    thread = threading.Thread(target=run_crawl_job, args=[route_id])
    thread.daemon = True # 设为守护线程（主程序关了它也会跟着关）
    thread.start() # 启动线程
    add_log("INFO", f"已触发后台立即执行：路线 ID {route_id}。")

def init_scheduler():
    """
    每次重启服务器（main.py 启动）时执行。
    负责把数据库里所有“开启”状态的路线，重新加回到调度器里继续跑。
    """
    active_routes = get_active_routes() # 从数据库拿所有开启的路线
    add_log("INFO", f"调度器初始化，共有 {len(active_routes)} 条活跃路线需要监控。")
    for route in active_routes:
        try:
            add_route_job(route) # 逐个加进去
        except Exception as e:
            add_log("ERROR", f"路线 ID {route['id']} 加入调度器失败: {str(e)}")

# 这段代码只有在你单独运行 python scheduler.py 时才会执行，用来测试的
if __name__ == "__main__":
    import time
    init_scheduler()
    print("调度器正在运行... 按 Ctrl+C 退出。")
    try:
        while True:
            time.sleep(1) # 主线程死循环睡觉，保持程序不退
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown() # 按下 Ctrl+C 后优雅地关闭调度器
