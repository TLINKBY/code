import sqlite3 # 导入 Python 内置的 SQLite 数据库库
import os # 导入操作系统接口，用于路径处理
import json # 导入 JSON 库
from datetime import datetime # 导入时间处理库

# 获取当前文件所在目录，并在该目录下生成数据库文件 tracker.db 的完整路径
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tracker.db")

def get_db_connection():
    """
    获取数据库连接
    """
    conn = sqlite3.connect(DB_PATH) # 连接 SQLite 数据库
    # 设置 row_factory 使得取出的数据行可以像字典一样通过列名访问数据 (例如 row['price'])
    conn.row_factory = sqlite3.Row 
    return conn

def init_db():
    """
    初始化数据库表结构。如果表不存在则创建它们。
    通常在程序第一次运行时调用。
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Create routes table (创建路线配置表)
    # 用于存储用户在网页端添加的所有需要监控的路线
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS routes (
        id INTEGER PRIMARY KEY AUTOINCREMENT, -- 路线唯一ID，自增
        departure TEXT NOT NULL, -- 出发地
        arrival TEXT NOT NULL, -- 目的地
        date TEXT NOT NULL, -- 出发日期
        target_price REAL, -- 目标心理价位
        interval_minutes INTEGER DEFAULT 30, -- 每次抓取检查的间隔分钟数
        is_active INTEGER DEFAULT 1, -- 是否开启监控（1=开启，0=暂停）
        created_at TEXT NOT NULL -- 路线创建时间
    )
    """)
    
    # Create prices table (创建价格记录表)
    # 用于存储爬虫每次抓取回来的航班价格数据
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS prices (
        id INTEGER PRIMARY KEY AUTOINCREMENT, -- 价格记录唯一ID
        route_id INTEGER, -- 关联的路线ID
        flight_number TEXT, -- 航班号
        airline TEXT, -- 航司名称
        departure_time TEXT, -- 起飞时间
        arrival_time TEXT, -- 降落时间
        price REAL, -- 抓取到的价格
        checked_at TEXT NOT NULL, -- 本次抓取的时间点
        is_transfer INTEGER DEFAULT 0, -- 是否中转（1=是，0=直飞）
        transit_visa TEXT, -- 过境签说明（如果有）
        screenshot_path TEXT, -- 爬虫截图在本地保存的路径
        FOREIGN KEY (route_id) REFERENCES routes (id) ON DELETE CASCADE -- 外键关联，当路线被删时，相关的价格记录也会自动删除
    )
    """)
    
    # Auto-migration for existing database files
    # 自动升级旧版本的数据库表结构。如果字段不存在就加上去，存在报错就忽略 (为了兼容旧版代码)
    try:
        cursor.execute("ALTER TABLE prices ADD COLUMN is_transfer INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE prices ADD COLUMN transit_visa TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE prices ADD COLUMN screenshot_path TEXT")
    except sqlite3.OperationalError:
        pass
    
    # Create settings table (创建设置表)
    # 用于存储通知配置，比如你的 Bark Token
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY, -- 设置项的键名
        value TEXT -- 设置项的值
    )
    """)
    
    # Create logs table (创建日志表)
    # 用于存储系统运行日志，供网页端展示
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL, -- 日志时间
        level TEXT, -- 日志级别 (INFO, ERROR, WARNING)
        message TEXT -- 日志内容
    )
    """)
    
    # Insert default settings if they don't exist (写入默认配置)
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('wechat_type', 'none')")
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('wechat_key', '')")
    
    conn.commit() # 提交所有改动
    conn.close() # 关闭数据库连接

# Log functions
def add_log(level, message):
    conn = get_db_connection()
    cursor = conn.cursor()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("INSERT INTO logs (timestamp, level, message) VALUES (?, ?, ?)", (timestamp, level, message))
    conn.commit()
    conn.close()
    print(f"[{timestamp}] [{level}] {message}")

def get_logs(limit=200):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM logs ORDER BY id DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def clear_logs():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM logs")
    conn.commit()
    conn.close()

# Routes functions
def add_route(departure, arrival, date, target_price, interval_minutes=30):
    conn = get_db_connection()
    cursor = conn.cursor()
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
        INSERT INTO routes (departure, arrival, date, target_price, interval_minutes, is_active, created_at)
        VALUES (?, ?, ?, ?, ?, 1, ?)
    """, (departure.upper(), arrival.upper(), date, target_price, interval_minutes, created_at))
    conn.commit()
    route_id = cursor.lastrowid
    conn.close()
    add_log("INFO", f"Added route: {departure} -> {arrival} on {date} (target: {target_price}, interval: {interval_minutes}m)")
    return route_id

def get_routes():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM routes ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_route(route_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM routes WHERE id = ?", (route_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_active_routes():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM routes WHERE is_active = 1")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def delete_route(route_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM routes WHERE id = ?", (route_id,))
    cursor.execute("DELETE FROM prices WHERE route_id = ?", (route_id,))
    conn.commit()
    conn.close()
    add_log("INFO", f"Deleted route ID: {route_id}")

def update_route_status(route_id, is_active):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE routes SET is_active = ? WHERE id = ?", (1 if is_active else 0, route_id))
    conn.commit()
    conn.close()
    status_str = "activated" if is_active else "paused"
    add_log("INFO", f"Route ID {route_id} status changed to {status_str}")

# Prices functions
def add_price_log(route_id, flight_number, airline, departure_time, arrival_time, price, is_transfer=0, transit_visa=None, screenshot_path=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    checked_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
        INSERT INTO prices (route_id, flight_number, airline, departure_time, arrival_time, price, checked_at, is_transfer, transit_visa, screenshot_path)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (route_id, flight_number, airline, departure_time, arrival_time, price, checked_at, is_transfer, transit_visa, screenshot_path))
    conn.commit()
    conn.close()

def get_price_history(route_id, limit=1000):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM prices 
        WHERE route_id = ? 
        ORDER BY checked_at ASC, price ASC
    """, (route_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_lowest_price_history(route_id):
    # Returns the lowest price per check timestamp for plotting
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT MIN(price) as lowest_price, checked_at 
        FROM prices 
        WHERE route_id = ? 
        GROUP BY checked_at 
        ORDER BY checked_at ASC
    """, (route_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

# Settings functions
def get_settings():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM settings")
    rows = cursor.fetchall()
    conn.close()
    return {row["key"]: row["value"] for row in rows}

def update_settings(settings_dict):
    conn = get_db_connection()
    cursor = conn.cursor()
    for key, val in settings_dict.items():
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(val)))
    conn.commit()
    conn.close()
    add_log("INFO", f"Settings updated: {settings_dict.keys()}")

# Initialize on import/run
init_db()
