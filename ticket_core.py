# -*- coding: utf-8 -*-
import requests
import re
import smtplib
import os
import random
import time
from email.mime.text import MIMEText
from email.header import Header
from datetime import datetime, timedelta
from dotenv import load_dotenv
import database as db

load_dotenv()

# 公共配置
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://kyfw.12306.cn/otn/leftTicket/init",
    "Host": "kyfw.12306.cn"
}

SMTP_CONFIG = {
    "server": os.getenv("SMTP_SERVER") or "smtp.qq.com",
    "port": int(os.getenv("SMTP_PORT") or 465),
    "user": os.getenv("SMTP_USER") or "",
    "password": os.getenv("SMTP_PASSWORD") or ""
}

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def get_initialized_session():
    session = requests.Session()
    session.headers.update(HEADERS)
    query_url = "https://kyfw.12306.cn/otn/leftTicket/query"
    try:
        init_url = "https://kyfw.12306.cn/otn/leftTicket/init"
        res = session.get(init_url, timeout=5)
        match = re.search(r"CLeftTicketUrl\s*=\s*'([^']+)'", res.text)
        if match:
            query_url = f"https://kyfw.12306.cn/otn/{match.group(1)}"
    except Exception:
        pass
    return session, query_url

def parse_train_info(item):
    try:
        parts = item.split('|')
        return {
            "code": parts[3],
            "start": parts[8],
            "end": parts[9],
            "seats": {
                "商务": parts[32], "一等": parts[31], "二等": parts[30],
                "软卧": parts[23], "硬卧": parts[28], "硬座": parts[29], "无座": parts[26]
            }
        }
    except: return None

def calc_time_diff(arrive_time, start_time):
    """计算两段时间间隔(分钟)"""
    try:
        fmt = "%H:%M"
        t1 = datetime.strptime(arrive_time, fmt)
        t2 = datetime.strptime(start_time, fmt)
        # 跨天处理：如果 t2 < t1，说明是第二天（暂简单假设跨天不超过24h）
        if t2 < t1:
            t2 += timedelta(days=1)
        return (t2 - t1).seconds / 60
    except:
        return 0

def send_notification_email(receiver, title, content):
    try:
        msg = MIMEText(content, 'html', 'utf-8')
        sender = SMTP_CONFIG['user']
        msg['From'] = Header("12306云监控", 'utf-8')
        msg['From'].append(f"<{sender}>", 'ascii')
        msg['To'] = Header("用户", 'utf-8')
        msg['Subject'] = Header(title, 'utf-8')
        
        smtp = smtplib.SMTP_SSL(SMTP_CONFIG['server'], SMTP_CONFIG['port'], timeout=10)
        smtp.login(SMTP_CONFIG['user'], SMTP_CONFIG['password'])
        smtp.sendmail(SMTP_CONFIG['user'], [receiver], msg.as_string())
        smtp.quit()
        return True
    except Exception as e:
        log(f"邮件发送失败: {e}")
        return False

def _fetch_trains(session, query_url, f_st, t_st, date):
    """内部通用查票函数"""
    params = {
        "leftTicketDTO.train_date": date,
        "leftTicketDTO.from_station": f_st,
        "leftTicketDTO.to_station": t_st,
        "purpose_codes": "ADULT"
    }
    try:
        # IP 保护：强制随机抖动
        sleep_time = random.uniform(2.0, 5.0)
        time.sleep(sleep_time)
        
        res = session.get(query_url, params=params, timeout=10)
        res_json = res.json()
        if res_json.get("data") and res_json.get("data").get("result"):
            raw_results = res_json["data"]["result"]
            trains = [parse_train_info(item) for item in raw_results]
            return [t for t in trains if t]
    except Exception as e:
        log(f"⚠️ 查询异常 ({f_st}->{t_st}): {e}")
    return []

def _check_seats(train, target_seats):
    """检查单个车次是否有指定席别余票"""
    valid_seats = []
    for s_name in target_seats:
        s_count = train['seats'].get(s_name)
        if s_count and s_count not in ['无', '']:
            valid_seats.append(f"{s_name}:{s_count}")
    return valid_seats

def generate_email_html(tickets_html, is_transfer=False):
    """生成统一的邮件 HTML"""
    title_text = "中转方案推荐" if is_transfer else "发现直达余票"
    return f"""
    <div style="background-color: #FBFBF6; padding: 40px; font-family: 'STSong', 'SimSun', serif; color: #293C55;">
        <div style="max-width: 600px; margin: 0 auto; background: #ffffff; border: 1px solid #e0e0e0; border-radius: 8px; box-shadow: 0 4px 15px rgba(0,0,0,0.05); overflow: hidden;">
            <div style="background-color: #293C55; color: #FBFBF6; padding: 25px; text-align: center;">
                <h2 style="margin: 0; font-size: 24px; letter-spacing: 4px; font-weight: normal;">12306 云监控提醒</h2>
            </div>
            <div style="padding: 35px; line-height: 1.8;">
                <p style="font-size: 18px; color: #D93D3B; font-weight: bold; border-bottom: 2px solid #F2A626; padding-bottom: 10px; display: inline-block; margin-top: 0;">
                    {title_text}
                </p>
                <p style="margin-top: 20px; font-family: 'Microsoft YaHei', sans-serif;">尊敬的用户，为您监控到以下车次已有余票，请尽快处理：</p>
                <div style="background-color: #F8F9FA; border-left: 4px solid #613D31; padding: 20px; margin: 25px 0; background-image: linear-gradient(to right, #f8f9fa, #ffffff);">
                    <ul style="margin: 0; padding-left: 20px; list-style-type: none; font-family: 'Microsoft YaHei', sans-serif; font-size: 16px;">
                        {tickets_html}
                    </ul>
                </div>
                <div style="font-size:13px; color:#999; margin-top:10px; background:#fff3cd; padding:10px; border-radius:4px;">
                    ⚠️ 为了保护服务器IP不被封禁，系统采用低频轮询策略。请勿手动频繁刷新，以免影响监控。
                </div>
                <div style="text-align: center; margin-top: 35px;">
                    <a href="https://kyfw.12306.cn/" style="background-color: #D93D3B; color: #ffffff; padding: 12px 30px; text-decoration: none; border-radius: 4px; font-weight: bold; display: inline-block; box-shadow: 0 2px 5px rgba(217,61,59,0.3);">
                        立即前往 12306 购票
                    </a>
                </div>
            </div>
            <div style="background-color: #FBFBF6; padding: 25px; text-align: right; border-top: 1px dotted #ccc; color: #666; font-size: 14px;">
                <p style="margin: 0; font-style: italic;">山水有相逢，愿您旅途愉快。</p>
                <p style="margin: 8px 0 0 0; font-weight: bold; color: #613D31; font-size: 16px;">
                    <span style="font-weight: normal; font-size: 12px; color: #999;">--</span> by 呼啦啦啦桃猪
                </p>
            </div>
        </div>
    </div>
    """

def query_and_notify(f_st, t_st, date, tasks_for_route):
    """直达查询"""
    # 1. 限流检查
    if not db.can_make_request(limit=2, window_seconds=60):
        log(f"🚦 触发限流 (直达)，跳过: {f_st}->{t_st}")
        return False, 0

    db.record_request()
    session, query_url = get_initialized_session()
    
    log(f"🔍 发起查询: {date} {f_st}->{t_st}")
    trains = _fetch_trains(session, query_url, f_st, t_st, date)
    
    notified_count = 0
    if trains:
        for task in tasks_for_route:
            task_id = task[0]
            target_seats = task[6].split(',')
            user_email = task[7]
            
            found_tickets = []
            for train in trains:
                valid_seats = _check_seats(train, target_seats)
                if valid_seats:
                    found_tickets.append(f"<b>{train['code']}</b> {train['start']}-{train['end']} ({' '.join(valid_seats)})")
            
            if found_tickets:
                tickets_html = "".join([f"<li style='margin-bottom:8px;'>{t}</li>" for t in found_tickets])
                content = generate_email_html(tickets_html, is_transfer=False)
                if send_notification_email(user_email, f"[有票] {date} {f_st}->{t_st}", content):
                    db.update_notification_time(task_id)
                    notified_count += 1
                    log(f"✅ 直达通知发送成功: {user_email} (任务进入3小时冷却期)")
    
    return True, notified_count

def query_transfer_and_notify(f_st, m_st, t_st, date, tasks_for_route):
    """中转查询 (双程)"""
    # 中转需要查两次，消耗双倍限流额度
    if not db.can_make_request(limit=4, window_seconds=60): # 稍微放宽一点窗口前检查，但消耗更多
        log(f"🚦 触发限流 (中转)，跳过: {f_st}->{m_st}->{t_st}")
        return False, 0
    
    session, query_url = get_initialized_session()
    
    # 第一程
    db.record_request()
    log(f"🔍 [中转-1] 查询: {date} {f_st}->{m_st}")
    trains_1 = _fetch_trains(session, query_url, f_st, m_st, date)
    
    if not trains_1:
        return True, 0 # 第一程没票就不用查第二程了，节省资源
        
    # 第二程
    db.record_request()
    log(f"🔍 [中转-2] 查询: {date} {m_st}->{t_st}")
    trains_2 = _fetch_trains(session, query_url, m_st, t_st, date)
    
    if not trains_2:
        return True, 0

    notified_count = 0
    for task in tasks_for_route:
        task_id = task[0]
        target_seats = task[6].split(',')
        user_email = task[7]
        
        found_plans = []
        for t1 in trains_1:
            seats_1 = _check_seats(t1, target_seats)
            if not seats_1: continue
            
            for t2 in trains_2:
                seats_2 = _check_seats(t2, target_seats)
                if not seats_2: continue
                
                # 检查中转时间 (>=40分钟)
                wait_min = calc_time_diff(t1['end'], t2['start'])
                if wait_min >= 40:
                    found_plans.append(
                        f"<b>{t1['code']} + {t2['code']}</b><br>"
                        f"<span style='color:#666;font-size:0.9em'>"
                        f"{f_st}({t1['start']}) → {m_st}({t1['end']}) [停{int(wait_min)}分] → {t_st}({t2['end']})"
                        f"</span><br>"
                        f"余票: {','.join(seats_1)} / {','.join(seats_2)}"
                    )
        
        if found_plans:
            # 限制邮件长度，最多显示前5个方案
            tickets_html = "".join([f"<li style='margin-bottom:15px; border-bottom:1px dashed #eee; padding-bottom:5px;'>{t}</li>" for t in found_plans[:5]])
            content = generate_email_html(tickets_html, is_transfer=True)
            if send_notification_email(user_email, f"[中转方案] {date} {f_st}->{m_st}->{t_st}", content):
                db.update_notification_time(task_id)
                notified_count += 1
                log(f"✅ 中转通知发送成功: {user_email} (任务进入3小时冷却期)")

    return True, notified_count
