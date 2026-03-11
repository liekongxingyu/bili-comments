import asyncio
import aiohttp
from aiohttp import web
import os
import time
import traceback
from bilibili_api import user, search, comment, Credential

# ================= 1. 核心配置 =================
# B 站凭证 (填入你的真实数据)
SESSDATA = "b3e01e6d%2C1785830789%2Cb5efe%2A21CjC-cpt2JXRsvVevr4MVHan01uvYW90KSlIiCBOphg9wubph9ouMk1j7s05RcdXZpaMSVnNvNFBqMEpDV0tjRmpEZzZJblItVjY0S2pORHZvcm00TFlVVGt6UGk4eFd0NnN6Y0lVcGRCeGFScVU4SEZua1pac3Y4UllsSnBmRzhhQWNRc09fS2RnIIEC"
BILI_JCT = "8b212b982cb43dfd0c5d1b480c169bf4"
BUVID3 = "80FD5AFD-0565-40F9-0F52-72097F2DC9C211760infoc"

# 监控目标
TARGET_UP_NAME = "加密太空漫游者LV"

# QQ 推送配置 (Zeabur 内部域名)
NAPCAT_URL = "http://napcat.zeabur.internal:3000"
NAPCAT_TOKEN = "Qyogemq8qPENf9gq"
TARGET_QQ = 1694881090
TARGET_GROUP = 0  # 默认私聊推送

# 监控频率 (秒)
MONITOR_INTERVAL = 60 

# ================= 2. 消息发送工具 =================
async def send_qq_notification(text):
    """底层推送逻辑"""
    headers = {
        "Authorization": f"Bearer {NAPCAT_TOKEN}",
        "Content-Type": "application/json"
    }
    endpoint = "/send_group_msg" if TARGET_GROUP != 0 else "/send_private_msg"
    payload = {
        "group_id" if TARGET_GROUP != 0 else "user_id": TARGET_GROUP or TARGET_QQ,
        "message": text
    }
    
    async with aiohttp.ClientSession() as session:
        try:
            url = f"{NAPCAT_URL.rstrip('/')}{endpoint}"
            async with session.post(url, json=payload, headers=headers, timeout=5) as r:
                if r.status == 200:
                    print(f"[{time.strftime('%H:%M:%S')}] ✅ QQ 消息发送成功")
                else:
                    print(f"[{time.strftime('%H:%M:%S')}] ❌ QQ 发送失败 HTTP {r.status}")
        except Exception as e:
            print(f"[{time.strftime('%H:%M:%S')}] ❌ NapCat 连接故障: {e}")

# ================= 3. 核心监控逻辑 (后台任务) =================
async def monitor_task(app):
    credential = Credential(sessdata=SESSDATA, bili_jct=BILI_JCT, buvid3=BUVID3)
    
    print(f"[{time.strftime('%H:%M:%S')}] ⚙️ 正在执行系统初始化...")

    # A. 搜索并联通 UP 主
    try:
        search_results = await search.search_by_type(TARGET_UP_NAME, search_type=search.SearchObjectType.USER)
        uid = search_results['result'][0]['mid']
        u = user.User(uid, credential=credential)
        print(f"[{time.strftime('%H:%M:%S')}] 🔗 目标锁定: {TARGET_UP_NAME} (UID: {uid})")
    except Exception as e:
        print(f"❌ 搜索初始化失败: {e}")
        return

    current_aid = None
    last_rpid = None
    is_startup = True # 标记是否为首次启动

    while True:
        try:
            # 1. 检测最新视频
            video_list = await u.get_videos()
            if not video_list.get('list', {}).get('vlist'):
                await asyncio.sleep(MONITOR_INTERVAL)
                continue

            latest_video = video_list['list']['vlist'][0]
            new_aid = latest_video['aid']
            
            # 切换视频锚点
            if new_aid != current_aid:
                current_aid = new_aid
                last_rpid = None 
                print(f"[{time.strftime('%H:%M:%S')}] 切换监控视频: {latest_video['title']}")

            # 2. 获取该视频的最新评论
            res = await comment.get_comments(
                oid=current_aid, 
                type_=comment.CommentResourceType.VIDEO, 
                order=comment.OrderType.TIME,
                credential=credential
            )
            
            replies = res.get('replies', [])
            if replies:
                # 寻找 UP 主本人的最新一条评论
                latest_up_comment = next((c for c in replies if str(c['member']['mid']) == str(uid)), None)
                
                if latest_up_comment:
                    rpid = str(latest_up_comment['rpid'])
                    text = latest_up_comment['content']['message']
                    
                    # --- 上线即推送逻辑 ---
                    if is_startup:
                        print(f"[{time.strftime('%H:%M:%S')}] 🚀 系统已上线，同步最新评论状态...")
                        startup_report = (
                            f"🚀 B站监控系统上线成功\n"
                            f"目标：{TARGET_UP_NAME}\n"
                            f"当前视频：{latest_video['title']}\n"
                            f"当前最新评论：\n{text[:50]}..."
                        )
                        await send_qq_notification(startup_report)
                        last_rpid = rpid
                        is_startup = False # 初始化完成
                    
                    # --- 正常监控推送 ---
                    elif rpid != last_rpid:
                        print(f"[{time.strftime('%H:%M:%S')}] 📢 发现新评论，准备推送...")
                        notification_text = (
                            f"🔔 B站评论更新\n"
                            f"UP主：{TARGET_UP_NAME}\n"
                            f"视频：{latest_video['title']}\n"
                            f"内容：{text}\n"
                            f"链接：https://www.bilibili.com/video/av{current_aid}"
                        )
                        await send_qq_notification(notification_text)
                        last_rpid = rpid
            
            # 如果是启动状态但没找到评论，也发个上线提醒
            if is_startup:
                await send_qq_notification(f"🚀 B站监控系统上线成功\n目标：{TARGET_UP_NAME}\n当前视频暂无本人评论。")
                is_startup = False

        except Exception:
            traceback.print_exc()

        await asyncio.sleep(MONITOR_INTERVAL)

# ================= 4. Web 服务器入口 =================
async def handle_health_check(request):
    return web.Response(text="Bili-Monitor Alive", status=200)

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

if __name__ == "__main__":
    app = create_app()
    # 动态获取 Zeabur 端口
    port = int(os.environ.get("PORT", 8080))
    print(f"[{time.strftime('%H:%M:%S')}] 🛡️ 服务器启动在端口 {port}")
    web.run_app(app, host='0.0.0.0', port=port, print=None)