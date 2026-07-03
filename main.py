import os # 导入操作系统接口
from contextlib import asynccontextmanager # 导入异步上下文管理器，用于 FastAPI 生命周期事件
from fastapi import FastAPI, HTTPException, BackgroundTasks # 导入 FastAPI 核心框架和后台任务库
from fastapi.staticfiles import StaticFiles # 用于提供静态网页文件（前端面板）
from fastapi.responses import FileResponse # 用于直接返回文件响应
from pydantic import BaseModel # 用于定义 API 请求体的数据结构（数据验证）
from typing import Optional # 用于声明可选的字段类型

import db # 导入我们自己写的数据库模块
import scheduler # 导入定时任务调度器模块

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI 应用程序的生命周期管理器
    这个函数在服务器启动时运行前面的一半，在服务器关闭时运行 yield 后面的一半
    """
    # Startup: Load settings and initialize scheduler (服务器启动时执行)
    db.init_db() # 确保数据库表已经创建
    db.add_log("SYSTEM", "Application starting, initializing scheduler...") # 记录启动日志
    scheduler.init_scheduler() # 把数据库里开启的路线任务统统加载到调度器里开始跑
    yield # 挂起，把控制权交还给 FastAPI 让它专心处理网页请求
    
    # Shutdown: Stop scheduler (服务器关闭时执行)
    db.add_log("SYSTEM", "Application shutting down, stopping scheduler...") # 记录关闭日志
    scheduler.scheduler.shutdown() # 优雅地关闭调度器，停止所有后台爬虫任务

# 创建 FastAPI 应用程序实例，指定标题和生命周期管理器
app = FastAPI(title="Ctrip Flight Price Tracker (Mobile)", lifespan=lifespan)

# ==========================================
# Pydantic schemas (定义 API 接口需要的数据结构，起到自动校验参数的作用)
# ==========================================

class RouteCreate(BaseModel):
    """创建新监控路线时接收的数据包格式"""
    departure: str # 出发地，必填
    arrival: str # 目的地，必填
    date: str # 出发日期，必填 (YYYY-MM-DD)
    target_price: Optional[float] = None # 目标心理价位，选填
    interval_minutes: Optional[int] = 30 # 检查间隔，默认 30 分钟

class RouteToggle(BaseModel):
    """切换路线开关状态时接收的数据包格式"""
    is_active: bool # true=开启，false=关闭

class SettingsUpdate(BaseModel):
    """更新设置时接收的数据包格式"""
    wechat_type: str # 推送通道类型 (如: bark, serverchan)
    wechat_key: str # 对应的设备的秘钥/Token

# ==========================================
# API Endpoints (定义供前端网页调用的各个后台接口)
# ==========================================

@app.get("/api/routes")
def list_routes():
    try:
        routes = db.get_routes()
        # For each route, append the latest checked price and time
        enhanced_routes = []
        for r in routes:
            history = db.get_price_history(r["id"])
            latest_price = None
            latest_time = None
            if history:
                latest_check = history[-1]["checked_at"]
                latest_flights = [f for f in history if f["checked_at"] == latest_check]
                if latest_flights:
                    latest_price = min(f["price"] for f in latest_flights)
                    latest_time = latest_check
            
            r_dict = dict(r)
            r_dict["latest_price"] = latest_price
            r_dict["latest_checked_at"] = latest_time
            enhanced_routes.append(r_dict)
        return enhanced_routes
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/routes")
def create_route(route: RouteCreate, background_tasks: BackgroundTasks):
    try:
        if not route.departure or not route.arrival or not route.date:
            raise HTTPException(status_code=400, detail="Departure, arrival, and date are required.")
            
        route_id = db.add_route(
            departure=route.departure,
            arrival=route.arrival,
            date=route.date,
            target_price=route.target_price,
            interval_minutes=route.interval_minutes
        )
        
        new_route = db.get_route(route_id)
        scheduler.add_route_job(new_route)
        scheduler.trigger_route_now_async(route_id)
        
        return new_route
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/routes/{route_id}")
def remove_route(route_id: int):
    try:
        route = db.get_route(route_id)
        if not route:
            raise HTTPException(status_code=404, detail="Route not found")
        scheduler.remove_route_job(route_id)
        db.delete_route(route_id)
        return {"status": "success", "message": f"Route ID {route_id} deleted."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/routes/{route_id}/toggle")
def toggle_route(route_id: int, toggle: RouteToggle):
    try:
        route = db.get_route(route_id)
        if not route:
            raise HTTPException(status_code=404, detail="Route not found")
            
        db.update_route_status(route_id, toggle.is_active)
        updated_route = db.get_route(route_id)
        
        if toggle.is_active:
            scheduler.add_route_job(updated_route)
            scheduler.trigger_route_now_async(route_id)
        else:
            scheduler.remove_route_job(route_id)
            
        return updated_route
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/routes/{route_id}/trigger")
def trigger_route(route_id: int):
    try:
        route = db.get_route(route_id)
        if not route:
            raise HTTPException(status_code=404, detail="Route not found")
        scheduler.trigger_route_now_async(route_id)
        return {"status": "success", "message": f"Manual check triggered for route ID {route_id}."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/routes/{route_id}/history")
def route_history(route_id: int):
    try:
        route = db.get_route(route_id)
        if not route:
            raise HTTPException(status_code=404, detail="Route not found")
        
        all_flights = db.get_price_history(route_id)
        lowest_trend = db.get_lowest_price_history(route_id)
        
        return {
            "route": route,
            "flights": all_flights,
            "trend": lowest_trend
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/settings")
def get_settings():
    try:
        return db.get_settings()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/settings")
def update_settings(settings: SettingsUpdate):
    try:
        db.update_settings({
            "wechat_type": settings.wechat_type,
            "wechat_key": settings.wechat_key
        })
        return {"status": "success", "message": "Settings updated."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/logs")
def list_logs():
    try:
        return db.get_logs()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

from scheduler import scheduler as aps_scheduler

@app.get("/api/jobs")
def get_jobs():
    jobs = aps_scheduler.get_jobs()
    return {"jobs": [{"id": j.id, "next_run_time": str(j.next_run_time)} for j in jobs]}

@app.post("/api/logs/clear")
def clear_logs():
    try:
        db.clear_logs()
        db.add_log("INFO", "System logs cleared by user.")
        return {"status": "success", "message": "Logs cleared."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Serve static dashboard frontend
static_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
os.makedirs(static_path, exist_ok=True)

# Mount the static directory
app.mount("/static", StaticFiles(directory=static_path), name="static")

@app.get("/")
def read_index():
    index_file = os.path.join(static_path, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"message": "Ctrip Flight Tracker API Server is running. Please create static/index.html to view the dashboard."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
