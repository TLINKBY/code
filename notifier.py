import requests # 导入网络请求库，用于向第三方推送服务器发送数据
from db import add_log, get_settings # 导入数据库配置和日志函数

def send_wechat_notification(title, content):
    """
    发送手机推送通知的主函数（历史原因函数名带了wechat，但现在支持多种推送）
    :param title: 通知栏标题
    :param content: 通知的具体长文本内容
    """
    # 从数据库获取用户在网页端填写的通知配置
    settings = get_settings()
    wechat_type = settings.get("wechat_type", "none") # 推送类型，比如 bark
    wechat_key = settings.get("wechat_key", "") # 对应的推送设备 Key 或 Token
    
    # 如果没配置类型，或者没填 Key，直接跳过不发通知
    if wechat_type == "none" or not wechat_key:
        add_log("WARNING", "推送提醒被跳过：因为您还未配置推送通道。")
        return False
        
    try:
        if wechat_type == "serverchan":
            # ServerChan (Server酱) - 微信公众号推送服务
            url = f"https://sctapi.ftqq.com/{wechat_key}.send"
            data = {
                "title": title, # 标题
                "desp": content # Markdown 内容
            }
            # 发起 POST 请求
            res = requests.post(url, data=data, timeout=10)
            if res.status_code == 200:
                add_log("INFO", "ServerChan (Server酱) 微信推送发送成功。")
                return True
            else:
                add_log("ERROR", f"ServerChan 发送失败，错误码 {res.status_code}: {res.text}")
                
        elif wechat_type == "pushdeer":
            # PushDeer - 另一种轻量级 iOS/快应用 推送服务
            url = "https://api2.pushdeer.com/message/push"
            params = {
                "pushkey": wechat_key,
                "text": title,
                "desp": content,
                "type": "markdown" # 告诉服务器这是 Markdown 格式
            }
            # 发起 GET 请求
            res = requests.get(url, params=params, timeout=10)
            if res.status_code == 200:
                result = res.json()
                # PushDeer 的接口比较特殊，返回 200 还要检查里面的 result 字段
                if result.get("content", {}).get("result"):
                    add_log("INFO", "PushDeer 推送发送成功。")
                    return True
                else:
                    add_log("ERROR", f"PushDeer 响应异常，虽然是200但内容失败: {result}")
            else:
                add_log("ERROR", f"PushDeer 发送失败，错误码 {res.status_code}: {res.text}")
                
        elif wechat_type == "bark":
            # Bark - 这是苹果 iOS 上非常受欢迎且免费的系统级原生推送工具
            # API 结构很简单： https://api.day.app/你的设备Token
            url = f"https://api.day.app/{wechat_key}"
            data = {
                "title": title, # 推送标题
                "body": content # 推送正文
            }
            # 向 Bark 官方服务器发 POST 请求
            res = requests.post(url, json=data, timeout=10)
            if res.status_code == 200:
                add_log("INFO", "Bark (iOS) 推送发送成功，您的手机应该已经响了。")
                return True
            else:
                add_log("ERROR", f"Bark 发送失败，错误码 {res.status_code}: {res.text}")
                
        else:
            add_log("WARNING", f"未知的推送通道类型: {wechat_type}，请检查配置。")
            
    # 捕获网络断开等各种异常
    except Exception as e:
        add_log("ERROR", f"发送推送通知时发生致命异常: {str(e)}")
        
    return False

# 下面是测试用的代码，只有当你手动在终端输入 python notifier.py test 时才会执行
if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        print("正在向您的手机发送测试推送...")
        # 触发一条假消息测试配置通不通
        send_wechat_notification("机票降价提醒测试", "这是一条来自机票监控助手的测试消息！")
    else:
        print("要测试的话，请带上参数运行，例如：python notifier.py test")
