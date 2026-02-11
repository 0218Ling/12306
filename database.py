import pymysql
import hashlib
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# ================= MySQL 配置 =================
MYSQL_CONFIG = {
    "host": os.getenv("MYSQL_HOST", "localhost"),
    "port": int(os.getenv("MYSQL_PORT", 3306)),
    "user": os.getenv("MYSQL_USER", "root"),
    "password": os.getenv("MYSQL_PASSWORD", ""),
    "database": os.getenv("MYSQL_DB", "ticket_monitor"),
    "charset": "utf8mb4"
}

def get_conn():
    """获取 MySQL 连接"""
    return pymysql.connect(
        host=MYSQL_CONFIG["host"],
        port=MYSQL_CONFIG["port"],
        user=MYSQL_CONFIG["user"],
        password=MYSQL_CONFIG["password"],
        database=MYSQL_CONFIG["database"],
        charset=MYSQL_CONFIG["charset"]
    )

def init_db():
    """初始化数据库表结构 (MySQL版)"""
    try:
        conn = get_conn()
        c = conn.cursor()
        
        # 用户表
        c.execute('''CREATE TABLE IF NOT EXISTS users (
                        username VARCHAR(255) PRIMARY KEY,
                        password_hash VARCHAR(255) NOT NULL,
                        email VARCHAR(255),
                        created_at DATETIME
                    )''')
        
        # 任务表
        c.execute('''CREATE TABLE IF NOT EXISTS tasks (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        username VARCHAR(255),
                        from_station VARCHAR(50),
                        to_station VARCHAR(50),
                        date_str VARCHAR(20),
                        train_types VARCHAR(255),
                        seat_types VARCHAR(255),
                        receiver_email VARCHAR(255),
                        status INT DEFAULT 1 COMMENT '1=监控中, 0=停止, 2=完成', 
                        created_at DATETIME,
                        last_check_time DATETIME,
                        last_notification_time DATETIME
                    )''')
        
        # 尝试添加 last_notification_time 字段 (兼容旧表)
        try:
            c.execute("ALTER TABLE tasks ADD COLUMN last_notification_time DATETIME")
        except Exception:
            pass 
            
        # 尝试添加 middle_station 字段 (兼容旧表 - 支持中转)
        try:
            c.execute("ALTER TABLE tasks ADD COLUMN middle_station VARCHAR(50) DEFAULT NULL")
        except Exception:
            pass

        # 请求日志表 (用于限流)
        c.execute('''CREATE TABLE IF NOT EXISTS request_logs (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        req_time DATETIME
                    )''')
        
        conn.commit()
        conn.close()
        print("✅ MySQL 数据库表结构初始化完成")
    except Exception as e:
        print(f"❌ 数据库连接失败，请检查配置: {e}")

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def register_user(username, password, email):
    conn = get_conn()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO users (username, password_hash, email, created_at) VALUES (%s, %s, %s, %s)", 
                  (username, hash_password(password), email, datetime.now()))
        conn.commit()
        return True
    except pymysql.err.IntegrityError:
        return False
    finally:
        conn.close()

def login_user(username, password):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE username=%s AND password_hash=%s", (username, hash_password(password)))
    user = c.fetchone()
    conn.close()
    return user

def add_task(username, from_st, to_st, date, t_types, s_types, email, middle_st=None):
    conn = get_conn()
    c = conn.cursor()
    c.execute('''INSERT INTO tasks (username, from_station, to_station, date_str, train_types, seat_types, receiver_email, created_at, status, middle_station)
                 VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 1, %s)''',
              (username, from_st, to_st, date, t_types, s_types, email, datetime.now(), middle_st))
    conn.commit()
    conn.close()

def get_user_tasks(username):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM tasks WHERE username=%s ORDER BY created_at DESC", (username,))
    tasks = c.fetchall()
    conn.close()
    return tasks

def delete_task(task_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM tasks WHERE id=%s", (task_id,))
    conn.commit()
    conn.close()

# --- 限流控制函数 ---

def can_make_request(limit=2, window_seconds=60):
    """
    检查是否可以发起请求
    逻辑：统计过去 window_seconds 秒内的请求记录数
    """
    conn = get_conn()
    c = conn.cursor()
    # 清理过期的日志 (保持表轻量)
    c.execute("DELETE FROM request_logs WHERE req_time < %s", (datetime.now() - timedelta(seconds=window_seconds*2),))
    conn.commit()
    
    # 检查当前窗口内的数量
    c.execute("SELECT COUNT(*) FROM request_logs WHERE req_time > %s", (datetime.now() - timedelta(seconds=window_seconds),))
    count = c.fetchone()[0]
    conn.close()
    
    return count < limit

def record_request():
    """记录一次请求"""
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT INTO request_logs (req_time) VALUES (%s)", (datetime.now(),))
    conn.commit()
    conn.close()

# --- 供后台 Worker 调用的专用函数 ---

def get_active_tasks():
    """获取所有状态为1(监控中)的任务"""
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM tasks WHERE status=1")
    tasks = c.fetchall()
    conn.close()
    return tasks

def update_notification_time(task_id):
    """更新最后通知时间"""
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE tasks SET last_notification_time=%s WHERE id=%s", (datetime.now(), task_id))
    conn.commit()
    conn.close()

def update_check_time(task_id):
    """更新最后检查时间 (用于控制轮询频率)"""
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE tasks SET last_check_time=%s WHERE id=%s", (datetime.now(), task_id))
    conn.commit()
    conn.close()

def mark_task_completed(task_id):
    """标记任务为已完成"""
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE tasks SET status=2 WHERE id=%s", (task_id,))
    conn.commit()
    conn.close()

# 尝试初始化 (自动执行，确保表存在)
init_db()

if __name__ == "__main__":
    pass