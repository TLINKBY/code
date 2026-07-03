# Agent Context

这个项目是一个本地运行的“携程 App 机票价格监控助手”。后端用 FastAPI 提供网页面板和 API，APScheduler 定时触发任务，核心爬虫用 `uiautomator2` 操控一台安卓手机上的携程 App，结果写入本地 SQLite 数据库 `tracker.db`，前端静态文件在 `static/`。

## 快速运行

- 工作目录：`/Users/kouunryuu/TLINK/tiket`
- 虚拟环境：`./venv`
- 启动服务：`./venv/bin/python main.py`
- 备用启动：`./venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000 --reload`
- 打开面板：`http://localhost:8000/`
- 单独测试爬虫：`./venv/bin/python mobile_crawler.py <出发城市> <到达城市> <YYYY-MM-DD>`
- 语法检查：`./venv/bin/python -m py_compile main.py db.py scheduler.py mobile_crawler.py notifier.py`

主要依赖已经安装在虚拟环境中：FastAPI、uvicorn、APScheduler、uiautomator2、Pillow、requests。当前没有 `requirements.txt`、`pyproject.toml`、README，也不是 git 仓库。

## 核心文件

- `main.py`：FastAPI 应用入口。初始化数据库和调度器，提供路线、历史、设置、日志、任务状态 API，并挂载 `static/`。
- `db.py`：SQLite 访问层。数据库文件固定为项目根目录的 `tracker.db`。导入时会执行 `init_db()`。
- `scheduler.py`：全局 APScheduler。每条路线是一个 interval job；用 `device_lock` 串行化手机控制，避免多个任务同时操作同一台手机。
- `mobile_crawler.py`：核心手机自动化。连接安卓设备，打开携程，选择城市和日期，点击查询，解析航班列表屏幕文字，必要时截图。
- `notifier.py`：推送通知。支持 `serverchan`、`pushdeer`、`bark`，配置保存在数据库 `settings` 表。
- `static/index.html`、`static/app.js`、`static/style.css`：单页控制台。通过 REST API 添加路线、启停、手动触发、查看价格趋势和手机截图。

## 数据流

1. 前端 `POST /api/routes` 添加路线。
2. `db.add_route()` 写入 `routes`，默认 `is_active=1`。
3. `scheduler.add_route_job()` 注册定时任务，并 `trigger_route_now_async()` 立即后台抓取一次。
4. `run_crawl_job()` 读取路线，拿 `device_lock`，调用 `scrape_ctrip_mobile()`。
5. 爬虫返回航班列表后，`add_price_log()` 写入 `prices`。
6. 如果最低价低于 `target_price`，调用 `send_wechat_notification()` 推送，并保存达标航班截图到 `static/target_*.png`。
7. 前端轮询 `/api/routes`、`/api/logs`、`/api/routes/{id}/history` 展示状态、日志、趋势和航班表。

## API 速查

- `GET /api/routes`：路线列表，附带最新最低价和最后检查时间。
- `POST /api/routes`：创建路线。请求体：`departure`、`arrival`、`date`、`target_price?`、`interval_minutes?`。
- `DELETE /api/routes/{route_id}`：删除路线和价格记录。
- `POST /api/routes/{route_id}/toggle`：启停路线。请求体：`is_active`。
- `POST /api/routes/{route_id}/trigger`：手动立即抓取。
- `GET /api/routes/{route_id}/history`：返回路线、所有价格记录、每次检查的最低价趋势。
- `GET/POST /api/settings`：读取/保存推送设置。
- `GET /api/logs`、`POST /api/logs/clear`：日志列表和清空。
- `GET /api/jobs`：APScheduler 当前任务和下次运行时间。

## 数据库表

- `routes`：`id`、`departure`、`arrival`、`date`、`target_price`、`interval_minutes`、`is_active`、`created_at`。
- `prices`：`route_id`、航班号、航司、起降时间、价格、检查时间、中转标记、过境签说明、截图路径。
- `settings`：键值配置，默认 `wechat_type=none`、`wechat_key=''`。
- `logs`：运行日志，前端默认显示最近 200 条。

## 爬虫实现要点

- `init_device()` 使用 `u2.connect()` 自动连接 USB 或局域网安卓设备。
- 连接设备后会调用 `configure_screen_awake()`，把熄屏时间设置为 30 分钟，并尝试开启插电常亮；关键点击、解析、截图、滑动前会调用 `ensure_screen_on()`，防止运行中黑屏。
- 操作 App 包名：`ctrip.android.view`。
- 城市选择优先用 content-desc：`depart city`、`arrival city`，失败后用固定坐标兜底。
- 日期选择依赖携程日历布局坐标计算：周日为第一列，`HEADER_TO_FIRST_ROW=84`，`ROW_HEIGHT=178`，`GRID_LEFT=13`，`GRID_WIDTH=1054`。
- 查询按钮不要用 `textContains="查询"`，因为会误点“最近查询”。现有代码使用 `description="do inquire"`、精确文本和坐标兜底。
- 航班解析来自一次性 `dump_hierarchy()` 得到的可访问控件文字，不只扫 `android.widget.TextView`，因为携程主票价可能用其他控件暴露。不要用 `for el in d()` 逐个遍历控件，复杂页面会卡住并占用设备锁。解析时按 Y 坐标聚类，过滤广告横幅和底部排序栏，再用正则提取价格、时间、航班号、中转/过境签信息。价格不要取同一行最小数字；携程会显示“已优惠 ¥100”这类优惠金额，应优先取右侧主票价。
- 每次抓取滑动 4 屏，按 `(flight_number, price)` 去重，最后按价格升序返回。
- 第一屏会保存路线专属截图 `static/screenshot_route_<route_id>.png`，并保留旧的全局调试截图 `static/screenshot.png`；达标价格会裁剪航班卡片保存为 `static/target_*.png`。

## 易碎点和注意事项

- 这是 UI 自动化项目，携程 App 页面、文案、content-desc、日历布局或屏幕分辨率变化都会影响稳定性。
- `scheduler.scheduler` 在模块导入时就 `start()`，FastAPI lifespan 里再加载活跃路线。改调度器时注意不要重复启动或关闭。
- 所有手机操作必须继续走 `device_lock`，否则并发任务会互相干扰。
- `db.py` 的 `init_db()` 导入即执行；写测试或脚本时会触碰真实 `tracker.db`。
- `tracker.db` 是真实运行数据，已有路线、价格和大量日志；不要随意删除或重建。
- `static/` 中有运行截图和调试截图，可能会被爬虫覆盖，尤其是 `static/screenshot.png`。
- 前端依赖外部 CDN：Google Fonts、FontAwesome、Chart.js。离线环境下图标/图表可能无法加载。

## 调试脚本

根目录有多个一次性调试脚本，主要用于观察携程 UI 或验证自动化流程：

- `debug_full_flow.py`、`debug_city_flow.py`、`debug_click_date.py`：流程/城市/日期选择调试。
- `debug_calendar.py`、`debug_calendar_hierarchy.py`、`calendar.xml`、`calendar_hierarchy.xml`：日历布局分析。
- `dump_current_screen.py`、`dump_inquire.py`、`dump_intl.py`、`debug_screen_dump.py`：屏幕和控件 dump。
- `test_intl_search.py`、`test_one_way.py`、`test_back_to_search.py`：携程页面入口和单程/查询测试。
- `test_aps.py`：APScheduler 基础测试。

这些脚本多数会直接连接手机并启动携程 App，运行前确认设备可用。

## 修改建议

- 后端接口改动后，检查 `static/app.js` 是否有对应 fetch 调用需要同步。
- 爬虫选择器或坐标改动后，优先用小脚本和截图验证，再接入 `scrape_ctrip_mobile()` 主流程。
- 数据库 schema 变更需要像现有 `prices` 字段一样保留轻量迁移，兼容已有 `tracker.db`。
- 如果要补依赖管理，优先从当前虚拟环境生成 `requirements.txt`，但要避免把调试/系统无关依赖误加进去。
