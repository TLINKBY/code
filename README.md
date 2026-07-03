# 携程 APP 机票监控助手

这是一个本地运行的机票价格监控工具。它通过 FastAPI 提供网页控制台，用 APScheduler 定时调度任务，并使用 `uiautomator2` 操控安卓手机上的携程 App 查询航班价格。查询结果会写入本地 SQLite 数据库，网页端可以查看路线、最新价格、历史趋势、运行日志和手机截图。

## 功能概览

- 添加多条机票监控路线，包括出发地、目的地、日期、目标价和监控间隔。
- 定时自动打开携程 App 查询机票价格。
- 支持手动立即触发某条路线查询。
- 查询结果写入本地 SQLite，保留历史价格记录。
- 网页端展示当前最低价、航班列表、价格趋势图和运行日志。
- 到达目标价格时支持推送通知。
- 支持 ServerChan、PushDeer、Bark 三种通知方式。
- 自动保存每条路线最近一次抓取截图。
- 遇到低价目标航班时保存裁剪后的航班卡片截图。
- 使用全局手机锁串行执行任务，避免多个监控任务同时操作同一台手机。

## 技术栈

- Python 3
- FastAPI
- Uvicorn
- APScheduler
- SQLite
- uiautomator2
- Pillow
- requests
- 原生 HTML/CSS/JavaScript
- Chart.js

## 项目结构

```text
.
├── main.py                 # FastAPI 入口，API 和静态页面服务
├── db.py                   # SQLite 初始化和数据访问层
├── scheduler.py            # APScheduler 定时任务和手机全局锁
├── mobile_crawler.py       # 携程 App 自动化、航班解析、截图
├── notifier.py             # ServerChan / PushDeer / Bark 推送
├── static/
│   ├── index.html          # 网页控制台
│   ├── app.js              # 前端交互逻辑
│   └── style.css           # 前端样式
├── requirements.txt        # Python 依赖
├── AGENTS.md               # 给 AI agent 快速恢复上下文的工程备忘
└── debug_*.py / test_*.py  # UI 自动化调试脚本
```

运行时会生成一些本地文件，这些文件不会提交到 Git：

```text
tracker.db                  # 本地 SQLite 数据库
server.log                  # 服务日志
static/screenshot*.png      # 手机截图
static/target_*.png         # 低价航班截图
__pycache__/                # Python 缓存
venv/                       # 虚拟环境
```

## 环境准备

### 1. Python 环境

建议使用虚拟环境：

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

如果你已经有项目里的 `venv/`，也可以直接使用：

```bash
./venv/bin/python main.py
```

### 2. 安卓手机准备

本项目依赖真实安卓手机上的携程 App。运行前需要：

1. 手机安装携程 App。
2. 开启开发者模式。
3. 开启 USB 调试。
4. 用 USB 连接电脑，并在手机上允许调试授权。
5. 确认 `uiautomator2` 能连接手机。

可以用下面的方式快速测试：

```bash
./venv/bin/python - <<'PY'
import uiautomator2 as u2
d = u2.connect()
print(d.device_info)
PY
```

如果能输出设备信息，说明连接正常。

### 3. 防止手机熄屏

爬虫连接手机后会尝试执行以下保护：

- 将系统熄屏时间设置为 30 分钟。
- 开启插电常亮。
- 在关键点击、解析、截图、滑动前检查屏幕是否亮着。
- 如果屏幕熄灭，会自动点亮并上滑解锁。
- 如果手机进入 PIN 锁屏页，可以通过环境变量 `ANDROID_UNLOCK_PIN` 自动输入数字 PIN。

仍然建议手机保持 USB 连接或充电，并关闭省电模式。部分 Android 机型在省电模式下会忽略常亮设置。

如果你的手机锁屏需要数字 PIN，可以这样启动：

```bash
ANDROID_UNLOCK_PIN=123456 ./venv/bin/python main.py
```

或：

```bash
export ANDROID_UNLOCK_PIN=123456
./venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
```

`ANDROID_UNLOCK_PIN` 只支持 4 到 12 位数字。不要把 PIN 写进代码、README、数据库或 Git 提交。

## 启动服务

开发运行：

```bash
./venv/bin/python main.py
```

或使用 Uvicorn：

```bash
./venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
```

打开网页控制台：

```text
http://localhost:8000/
```

## 使用流程

1. 打开网页控制台。
2. 在左侧填写出发城市、到达城市、出发日期、目标价格和监控间隔。
3. 点击开始监控。
4. 系统会立即触发一次手机 App 查询。
5. 后续按设置的间隔自动查询。
6. 在路线卡片中可以查看最新价格、手动触发、暂停、删除。
7. 点击路线卡片可以查看价格趋势、当前航班列表和手机截图。

## 通知配置

网页控制台支持配置通知渠道：

- `none`：不发送通知。
- `serverchan`：ServerChan / Server 酱。
- `pushdeer`：PushDeer。
- `bark`：Bark iOS 推送。

配置会写入 SQLite 的 `settings` 表。

当某条路线的最低价小于或等于目标价时，系统会发送通知，并尽量保存对应航班卡片截图。

## API 说明

### 路线

```http
GET /api/routes
```

返回所有监控路线，并附带最新最低价和最后检查时间。

```http
POST /api/routes
```

创建路线。

请求体示例：

```json
{
  "departure": "成都",
  "arrival": "东京",
  "date": "2026-09-26",
  "target_price": 1800,
  "interval_minutes": 30
}
```

```http
DELETE /api/routes/{route_id}
```

删除路线及其价格记录。

```http
POST /api/routes/{route_id}/toggle
```

启停路线。

请求体示例：

```json
{
  "is_active": false
}
```

```http
POST /api/routes/{route_id}/trigger
```

立即触发某条路线查询。

```http
GET /api/routes/{route_id}/history
```

返回路线详情、航班价格记录和最低价趋势。

### 设置

```http
GET /api/settings
POST /api/settings
```

读取和保存通知设置。

### 日志

```http
GET /api/logs
POST /api/logs/clear
```

读取和清空运行日志。

### 调度任务

```http
GET /api/jobs
```

查看 APScheduler 当前任务和下次运行时间。

## 数据库

数据库文件是项目根目录的 `tracker.db`，会在首次运行时自动创建。

主要表：

- `routes`：监控路线配置。
- `prices`：每次抓取到的航班价格。
- `settings`：通知渠道和 key。
- `logs`：运行日志。

`tracker.db` 是本地运行数据，默认被 `.gitignore` 排除。

## 爬虫实现要点

### 设备连接

`mobile_crawler.py` 使用 `u2.connect()` 自动连接 USB 或局域网安卓设备。

### 页面导航

流程大致是：

1. 唤醒并解锁手机。
2. 启动携程 App：`ctrip.android.view`。
3. 关闭开屏广告、弹窗和系统授权弹窗。
4. 点击机票入口。
5. 确保选择单程。
6. 输入出发城市和到达城市。
7. 选择日期。
8. 点击查询。
9. 解析航班列表并滚动多屏。

### 日期选择

携程日历不是标准控件，项目里通过月份标题和固定日历布局计算日期坐标。

关键参数：

```python
HEADER_TO_FIRST_ROW = 84
ROW_HEIGHT = 178
GRID_LEFT = 13
GRID_WIDTH = 1054
```

如果携程 App UI 或手机分辨率变化，日期点击可能需要重新校准。

### 航班解析

航班解析使用一次性 `dump_hierarchy()` 获取可访问控件文字，然后按 Y 坐标聚类为航班行。

注意事项：

- 不只解析 `android.widget.TextView`，因为主票价可能通过其他控件暴露。
- 不使用 `for el in d()` 逐个访问控件，因为复杂页面可能卡住并占用设备锁。
- 价格不能简单取同一行最小数字。携程会显示 `已优惠 ¥100` 这类优惠金额，应优先取右侧主票价。
- 会过滤底部排序栏、广告横幅和推荐卡片，避免误识别。

## 常用命令

语法检查：

```bash
./venv/bin/python -m py_compile main.py db.py scheduler.py mobile_crawler.py notifier.py
```

单独测试爬虫：

```bash
./venv/bin/python mobile_crawler.py 成都 东京 2026-09-26
```

查看 Git 状态：

```bash
git status
```

推送到远程仓库：

```bash
git push
```

## 常见问题

### 1. 程序看起来不跑了

先检查服务和任务：

```bash
lsof -nP -iTCP:8000 -sTCP:LISTEN
curl http://127.0.0.1:8000/api/jobs
```

再看网页日志或数据库日志。这个项目用全局手机锁串行执行任务，如果某个任务卡住，后面的任务会等待。

### 2. 搜索方向看起来反了

项目会为每条路线保存专属截图：

```text
static/screenshot_route_<route_id>.png
```

不要只看全局 `static/screenshot.png`，它会被任意路线的最新抓取覆盖。

### 3. 票价被识别成 100

携程页面可能显示 `已优惠 ¥100`。当前解析逻辑会优先选择右侧主票价，并排除优惠金额。如果仍然出现误识别，需要保存当次截图和 UI hierarchy 继续校准。

### 4. 手机自动熄屏

项目会自动延长熄屏时间并尝试插电常亮。仍建议：

- 手机保持 USB 连接。
- 关闭省电模式。
- 确保锁屏不需要复杂密码或人脸识别。
- 如果必须使用数字 PIN，启动服务时设置 `ANDROID_UNLOCK_PIN`。

### 5. 连接不上手机

确认：

- USB 调试已开启。
- 手机上已允许当前电脑调试。
- 数据线支持数据传输。
- 携程 App 已安装。
- `uiautomator2` 能输出设备信息。

## Git 说明

仓库地址：

```text
git@github-tlinkby:TLINKBY/code.git
```

项目 `.gitignore` 已排除运行数据、数据库、截图、日志和虚拟环境。

## 维护建议

- 改 API 时同步检查 `static/app.js`。
- 改数据库字段时保留自动迁移，避免破坏已有 `tracker.db`。
- 改携程 UI 自动化时，先用调试脚本验证选择器和坐标。
- 改航班解析时，优先基于真实截图和 UI hierarchy 做回归测试。
- 不要提交真实运行截图、数据库、通知 key 或手机设备敏感信息。
