# -*- coding: utf-8 -*-
import time
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
import database as db
import ticket_core 

# ================= 配置区 =================
BATCH_INTERVAL = 15  # 心跳间隔缩短为 15秒 (用于快速发现新任务)
TASK_POLL_INTERVAL = 60 * 10  # 单个任务轮询间隔 (10分钟)
MAX_WORKERS = 3

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def process_route_group(route_key, task_list):
    """Worker 调用的处理函数"""
    f_st, t_st, date, m_st = route_key
    
    # 随机延迟防止并发瞬间撞墙
    time.sleep(random.uniform(1.0, 5.0))
    
    # 执行查询
    if m_st:
        success, count = ticket_core.query_transfer_and_notify(f_st, m_st, t_st, date, task_list)
    else:
        success, count = ticket_core.query_and_notify(f_st, t_st, date, task_list)
    
    # 无论成功与否，只要尝试过查询，就更新检查时间
    # 这样可以防止任务被无限重试，符合 TASK_POLL_INTERVAL 限制
    if success: # 如果因限流失败(success=False)，则不更新时间，以便下轮重试(受限流锁控制)
        for task in task_list:
            db.update_check_time(task[0])
        log(f"✅ 已更新 {len(task_list)} 个任务的检查时间")

    if not success:
        log(f"⚠️ 线路 {f_st}->{t_st} 因限流未执行")

def worker_loop():
    log("🚀 后台监控服务已启动 (智能轮询版)...")
    db.init_db()
    
    while True:
        try:
            all_tasks = db.get_active_tasks()
        except Exception as e:
            log(f"❌ DB错误: {e}")
            time.sleep(5)
            continue
        
        if not all_tasks:
            # 即使没任务也只睡短一点，防止刚加任务要等很久
            time.sleep(10)
            continue
        
        # 1. 筛选需要执行的任务
        tasks_to_process = []
        current_time = datetime.now()
        
        for task in all_tasks:
            t_id = task[0]
            # 解析 last_check_time (假设第11个字段是 created, 12是last_check... 需兼容)
            # 最好直接根据结构取。
            # 结构: id(0), user(1), f(2), t(3), date(4), tt(5), st(6), email(7), status(8), 
            #       created(9), last_check(10), last_notify(11), middle(12)
            
            last_check = task[10]
            last_notify = task[11]

            # --- 检查1: 是否有票刚通知过 (3小时冷却) ---
            if last_notify:
                if isinstance(last_notify, str):
                    try: last_notify = datetime.strptime(last_notify, "%Y-%m-%d %H:%M:%S")
                    except: pass
                if isinstance(last_notify, datetime):
                    if current_time - last_notify < timedelta(hours=3):
                        # 冷却中，直接跳过
                        continue

            # --- 检查2: 是否刚查过 (10分钟轮询间隔) ---
            # 如果 last_check 为 None，说明是新任务，立即执行
            should_run = True
            if last_check:
                if isinstance(last_check, str):
                    try: last_check = datetime.strptime(last_check, "%Y-%m-%d %H:%M:%S")
                    except: pass
                if isinstance(last_check, datetime):
                    if current_time - last_check < timedelta(seconds=TASK_POLL_INTERVAL):
                        should_run = False
            
            if should_run:
                tasks_to_process.append(task)
        
        if not tasks_to_process:
            # 没有需要跑的任务，安静休眠
            # log(f"💤 暂无待办任务，待机中...") 
            time.sleep(BATCH_INTERVAL)
            continue

        log(f"⚡ 发现 {len(tasks_to_process)} 个待执行任务...")

        # 2. 分组
        grouped_tasks = {}
        for task in tasks_to_process:
            # task[12] 是 middle_station
            m_st = task[12] if len(task) > 12 else None
            key = (task[2], task[3], task[4], m_st) 
            if key not in grouped_tasks: grouped_tasks[key] = []
            grouped_tasks[key].append(task)

        # 3. 执行
        route_keys = list(grouped_tasks.keys())
        for i, r_key in enumerate(route_keys):
            process_route_group(r_key, grouped_tasks[r_key])
            
            # 任务间稍微间隔，防止瞬间并发
            if i < len(route_keys) - 1:
                time.sleep(random.uniform(5, 10))

        log(f"✅ 本轮执行完毕，休眠 {BATCH_INTERVAL} 秒...\n")
        time.sleep(BATCH_INTERVAL)

if __name__ == "__main__":
    worker_loop()