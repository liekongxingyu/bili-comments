import asyncio
import aiohttp
from aiohttp import web
import os
import time
import traceback
from bilibili_api import user, comment, Credential

# ================= 1. 核心配置 =================
# B 站凭证 (请确保这三个参数有效)
SESSDATA = "b3e01e6d%2C1785830789%2Cb5efe%2A21CjC-cpt2JXRsvVevr4MVHan01uvYW90KSlIiCBOphg9wubph9ouMk1j7s05RcdXZpaMSVnNvNFBqMEpDV0tjRmpEZzZJblItVjY0S2pORHZvcm00TFlVVGt6UGk4eFd0NnN6Y0lVcGRCeGFScVU4SEZua1pac3Y4UllsSnBmRzhhQWNRc09fS2RnIIEC"
BILI_JCT = "8b212b982cb43dfd0c5d1b480c169bf4"
BUVID3 = "80FD5AFD-0565-40F9-0F52-72097F2DC9C211760infoc"

# 监控目标：加密太空漫游者LV
TARGET_UID = 354689564  

# QQ 推送配置
# 注意：在 Zeabur 内部使用 .internal 域名；在本地 Docker 测试请改为 host.docker.internal
NAPCAT_URL = "http://napcat-lekong.zeabur.internal:3000"
NAPCAT_TOKEN = "Qyogemq8qPENf9gq"
TARGET_QQ = 1694881090

# 监控频率 (秒)
MONITOR_INTERVAL = 60 

# ================= 2. 监控核心逻辑 =================
async def monitor_task(app):
    """后台持续运行的监控循环"""
    credential = Credential(sessdata=SESSDATA, bili_jct=BILI_JCT, buvid3=BUVID3)
    u = user.User(TARGET_UID, credential=credential)
    last_rpid = None
    
    print(f"[{time.strftime('%H:%M:%S')}] ⚙️ 后台监控已就绪，目标 UID: {TARGET_UID}")

    while True:
        try:
            # 1. 获取最新视频
            v_data = await u.get_videos()
            if v_data.get('list', {}).get('vlist'):
                latest_v = v_data['list']['vlist'][0]
                aid = latest_v['aid']
                
                # 2. 获取最新评论
                c_data = await comment.get_comments(
                    oid=aid, 
                    type_=comment.CommentResourceType.VIDEO, 
                    order=comment.OrderType.TIME, 
                    credential=credential
                )
                replies = c_data.get('replies') or []
                
                # 3. 筛选 UP 主本人的评论
                up_comment = next((c for c in replies if str(c['member']['mid']) == str(TARGET_UID)), None)
                
                if up_comment:
                    rpid = str(up_comment['rpid'])
                    if rpid != last_rpid:
                        # 启动后的第一次检测只记录 ID，不发送推送
                        if last_rpid is not None:
                            content = up_comment['content']['message']
                            print(f"[{time.strftime('%H:%M:%S')}] 📢 发现新动态，准备推送 QQ")
                            
                            # 执行推送
                            async with aiohttp.ClientSession() as session:
                                headers = {"Authorization": f"Bearer {NAPCAT_TOKEN}"}
                                payload = {
                                    "message": f"🔔 B站评论提醒\nUP: 加密太空漫游者\n内容: {content}\n链接: https://www.bilibili.com/video/av{aid}",
                                    "user_id": TARGET_QQ
                                }
                                await session.post(f"{NAPCAT_URL}/send_private_msg", json=payload, headers=headers, timeout=5)
                        
                        last_rpid = rpid
        except Exception as e:
            print(f"[{time.strftime('%H:%M:%S')}] 监控轮询异常: {e}")
        
        # 按照设定频率休眠
        await asyncio.sleep(MONITOR_INTERVAL)

# ================= 3. Web 服务器逻辑 (应对 Zeabur 检查) =================
async def handle_home(request):
    """健康检查入口"""
    return web.Response(text=f"Bot is Alive. Server Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")

async def start_background_tasks(app):
    """服务器启动时挂载后台任务"""
    app['monitor_job'] = asyncio.create_task(monitor_task(app))

async def cleanup_background_tasks(app):
    """服务器关闭时清理任务"""
    app['monitor_job'].cancel()
    await app['monitor_job']

def create_app():
    """创建 aiohttp 应用实例"""
    app = web.Application()
    app.add_routes([web.get('/', handle_home)])
    app.on_startup.append(start_background_tasks)
    app.on_cleanup.append(cleanup_background_tasks)
    return app

# ================= 4. 执行入口 =================
if __name__ == "__main__":
    try:
        # 读取端口，Zeabur 默认通过环境变量 PORT 传递
        port = int(os.environ.get("PORT", 8080))
        app = create_app()
        print(f"[{time.strftime('%H:%M:%S')}] 🛡️ Web 保活服务器正在启动，端口: {port}")
        web.run_app(app, host='0.0.0.0', port=port, print=None)
    except Exception:
        traceback.print_exc()