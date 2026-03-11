import asyncio
import aiohttp
from aiohttp import web
import os
import time
import traceback
from bilibili_api import user, search, comment, Credential

# --- 1. 配置区域 (维持不变) ---
SESSDATA = "b3e01e6d%2C1785830789%2Cb5efe%2A21CjC-cpt2JXRsvVevr4MVHan01uvYW90KSlIiCBOphg9wubph9ouMk1j7s05RcdXZpaMSVnNvNFBqMEpDV0tjRmpEZzZJblItVjY0S2pORHZvcm00TFlVVGt6UGk4eFd0NnN6Y0lVcGRCeGFScVU4SEZua1pac3Y4UllsSnBmRzhhQWNRc09fS2RnIIEC"
BILI_JCT = "8b212b982cb43dfd0c5d1b480c169bf4"
BUVID3 = "80FD5AFD-0565-40F9-0F52-72097F2DC9C211760infoc"

# NapCat 配置 (Zeabur 内部通信建议使用 .internal 域名)
NAPCAT_URL = "http://napcat-lekong.zeabur.internal:3000"
NAPCAT_TOKEN = "LWgNFcEocsUjtuNV"
TARGET_QQ = 1694881090
TARGET_GROUP = 0
MONITOR_INTERVAL = 60

# --- 2. 发送 QQ 消息的函数 ---
async def send_qq_notification(text):
    headers = {
        "Authorization": f"Bearer {NAPCAT_TOKEN}",
        "Content-Type": "application/json"
    }
    if TARGET_GROUP != 0:
        endpoint = "/send_group_msg"
        payload = {"group_id": TARGET_GROUP, "message": text}
    else:
        endpoint = "/send_private_msg"
        payload = {"user_id": TARGET_QQ, "message": text}
        
    async with aiohttp.ClientSession() as session:
        try:
            url = f"{NAPCAT_URL.rstrip('/')}{endpoint}"
            async with session.post(url, json=payload, headers=headers, timeout=5) as response:
                if response.status == 200:
                    print(f"[{time.strftime('%H:%M:%S')}] ✅ QQ 通知发送成功")
                else:
                    print(f"[{time.strftime('%H:%M:%S')}] ❌ 发送失败：HTTP {response.status}")
        except Exception as e:
            print(f"[{time.strftime('%H:%M:%S')}] ❌ 连接 NapCat 失败: {e}")

# --- 3. 核心监控逻辑 (后台任务) ---
async def monitor_task(app):
    credential = Credential(sessdata=SESSDATA, bili_jct=BILI_JCT, buvid3=BUVID3)
    up_name = "加密太空漫游者LV"
    
    print(f"--- 后台监控启动 ---")
    
    # 初始获取 UID
    try:
        search_results = await search.search_by_type(up_name, search_type=search.SearchObjectType.USER)
        uid = search_results['result'][0]['mid']
        u = user.User(uid, credential=credential)
        print(f"已联通 UP 主: {up_name} (UID: {uid})")
    except Exception as e:
        print(f"初始化搜索失败: {e}")
        return

    current_aid = None
    last_rpid = None

    while True:
        try:
            # 检测最新视频
            video_list = await u.get_videos()
            if video_list.get('list', {}).get('vlist'):
                latest_video = video_list['list']['vlist'][0]
                new_aid = latest_video['aid']
                
                if new_aid != current_aid:
                    current_aid = new_aid
                    last_rpid = None 
                    print(f"[{time.strftime('%H:%M:%S')}] 监控新视频: {latest_video['title']}")

                # 获取评论
                res = await comment.get_comments(
                    oid=current_aid, 
                    type_=comment.CommentResourceType.VIDEO, 
                    order=comment.OrderType.TIME,
                    credential=credential
                )
                
                replies = res.get('replies', [])
                if replies:
                    # 寻找第一条属于 UP 主的评论
                    latest_up_comment = next((c for c in replies if str(c['member']['mid']) == str(uid)), None)
                    
                    if latest_up_comment:
                        rpid = str(latest_up_comment['rpid'])
                        if rpid != last_rpid:
                            # 第一次运行不推送，只记录
                            if last_rpid is not None:
                                text = latest_up_comment['content']['message']
                                print(f"[{time.strftime('%H:%M:%S')}] 发现新评论: {text[:20]}...")
                                
                                notification_text = (
                                    f"🔔 B站评论提醒\nUP主：{up_name}\n内容：{text}\n"
                                    f"链接：https://www.bilibili.com/video/av{current_aid}"
                                )
                                await send_qq_notification(notification_text)
                            last_rpid = rpid
        except Exception:
            traceback.print_exc()

        await asyncio.sleep(MONITOR_INTERVAL)

# --- 4. Web 路由逻辑 ---
async def handle_health_check(request):
    return web.Response(text="Bili-Monitor is Running", status=200)

async def start_background_tasks(app):
    app['monitor_job'] = asyncio.create_task(monitor_task(app))

async def cleanup_background_tasks(app):
    app['monitor_job'].cancel()
    await app['monitor_job']

def create_app():
    app = web.Application()
    app.router.add_get('/', handle_health_check)
    app.on_startup.append(start_background_tasks)
    app.on_cleanup.append(cleanup_background_tasks)
    return app

# --- 5. 执行入口 ---
if __name__ == "__main__":
    app = create_app()
    port = int(os.environ.get("PORT", 8080))
    print(f"Web 服务器启动在端口: {port}")
    web.run_app(app, host='0.0.0.0', port=port, print=None)