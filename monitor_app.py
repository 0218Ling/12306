import streamlit as st
import database as db
from datetime import datetime, timedelta
import requests
import re
import time
import ticket_core  # 引入核心库，用于立即查询

# ================= 基础配置 =================
st.set_page_config(page_title="12306 云监控服务", page_icon="🚄", layout="wide")

# --- 弹窗逻辑 ---
@st.dialog("⚠️ 特别声明")
def show_disclaimer():
    st.markdown("""
    <div style='font-family: "Microsoft YaHei", sans-serif; line-height: 1.6;'>
        <p>本工具仅供技术学习与小范围交流使用。</p>
        <p style='color: #D93D3B; font-weight: bold;'>监控数据仅供参考，购票请务必以 12306 官方信息为准。</p>
        <hr style='margin: 15px 0; border: none; border-top: 1px dashed #ccc;'>
        <div style='text-align: right; font-family: "STSong", serif; color: #613D31; font-weight: bold;'>
            By 呼啦啦啦桃猪
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    if st.button("我知道了", type="primary", use_container_width=True):
        st.session_state["has_seen_disclaimer"] = True
        st.rerun()

if "has_seen_disclaimer" not in st.session_state:
    show_disclaimer()

STATION_JS_URL = "https://kyfw.12306.cn/otn/resources/js/framework/station_name.js"
HEADERS = {"User-Agent": "Mozilla/5.0"}

@st.cache_data
def get_stations():
    try:
        res = requests.get(STATION_JS_URL, headers=HEADERS)
        res.encoding = 'utf-8'
        stations = {}
        for part in res.text.split('@'):
            if not part: continue
            infos = part.split('|')
            if len(infos) > 2: stations[infos[1]] = infos[2]
        return stations
    except Exception: return {}

# ================= 登录/注册逻辑 =================
if 'user' not in st.session_state:
    st.session_state.user = None

def login_page():
    st.title("🚄 12306 云监控 - 用户登录")
    
    tab1, tab2 = st.tabs(["登录", "注册新账号"])
    
    with tab1:
        username = st.text_input("用户名", key="l_user")
        password = st.text_input("密码", type="password", key="l_pass")
        if st.button("登录", type="primary"):
            user = db.login_user(username, password)
            if user:
                st.session_state.user = user[0] # 保存用户名
                st.session_state.email = user[2]
                st.rerun()
            else:
                st.error("用户名或密码错误")

    with tab2:
        new_user = st.text_input("设置用户名", key="r_user")
        new_pass = st.text_input("设置密码", type="password", key="r_pass")
        new_email = st.text_input("默认接收邮箱", key="r_email")
        if st.button("注册"):
            if db.register_user(new_user, new_pass, new_email):
                st.success("注册成功！请前往登录页登录。")
            else:
                st.error("用户名已存在")

# ================= 主控制台 =================
def main_dashboard():
    st.sidebar.title(f"👋 欢迎, {st.session_state.user}")
    if st.sidebar.button("退出登录"):
        st.session_state.user = None
        st.rerun()
    
    stations = get_stations()
    if not stations: st.error("无法加载车站数据"); return

    st.title("🚄 任务管理看板")
    
    # --- 新增任务区域 ---
    with st.expander("➕ 新增监控任务", expanded=True):
        st.warning("⚠️ **系统提示**：为防止服务器 IP 被 12306 封禁，后台采用**低频随机轮询**策略（直达约 30s/次，中转约 60s/次）。请勿频繁手动刷新，感谢配合。")
        
        tab_direct, tab_transfer = st.tabs(["直达监控", "中转监控"])
        
        # === 直达监控 Tab ===
        with tab_direct:
            c1, c2, c3 = st.columns(3)
            f_city = c1.selectbox("出发地", list(stations.keys()), index=list(stations.keys()).index("南昌") if "南昌" in stations else 0, key="d_f")
            t_city = c2.selectbox("目的地", list(stations.keys()), index=list(stations.keys()).index("邯郸") if "邯郸" in stations else 0, key="d_t")
            date_obj = c3.date_input("出发日期", min_value=datetime.today(), key="d_date")
            
            c4, c5 = st.columns(2)
            train_types = c4.multiselect("车型", ["高铁(G/C)", "动车(D)", "普速(Z/T/K)"], default=["高铁(G/C)", "动车(D)", "普速(Z/T/K)"], key="d_tt")
            seat_types = c5.multiselect("目标席别", ["二等", "一等", "商务", "硬卧", "软卧", "硬座", "无座"], default=["二等", "硬卧"], key="d_st")
            
            recv_email = st.text_input("接收通知邮箱", value=st.session_state.email, key="d_email")
            
            if st.button("🚀 提交直达任务", type="primary"):
                if not train_types or not seat_types:
                    st.error("请至少选择一种车型和席别")
                else:
                    db.add_task(st.session_state.user, stations[f_city], stations[t_city], 
                               date_obj.strftime("%Y-%m-%d"), 
                               ",".join(train_types), ",".join(seat_types), recv_email)
                    st.success("✅ 直达任务已保存！")
                    time.sleep(1)
                    st.rerun()

        # === 中转监控 Tab ===
        with tab_transfer:
            c1, c2, c3, c4 = st.columns(4)
            tf_f = c1.selectbox("出发地", list(stations.keys()), index=0, key="t_f")
            tf_m = c2.selectbox("中转地", list(stations.keys()), index=list(stations.keys()).index("武汉") if "武汉" in stations else 0, key="t_m")
            tf_t = c3.selectbox("目的地", list(stations.keys()), index=1, key="t_t")
            tf_date = c4.date_input("出发日期", min_value=datetime.today(), key="t_date")

            c5, c6 = st.columns(2)
            tf_tt = c5.multiselect("车型", ["高铁(G/C)", "动车(D)", "普速(Z/T/K)"], default=["高铁(G/C)", "动车(D)"], key="t_tt")
            tf_st = c6.multiselect("目标席别", ["二等", "一等", "硬卧"], default=["二等"], key="t_st")
            
            tf_email = st.text_input("接收通知邮箱", value=st.session_state.email, key="t_email")

            if st.button("🚀 提交中转任务", type="primary"):
                if not tf_tt or not tf_st:
                    st.error("请至少选择一种车型和席别")
                elif tf_f == tf_m or tf_m == tf_t or tf_f == tf_t:
                    st.error("出发、中转、目的站不能相同")
                else:
                    # 存入数据库，传入 middle_station
                    db.add_task(st.session_state.user, stations[tf_f], stations[tf_t], 
                               tf_date.strftime("%Y-%m-%d"), 
                               ",".join(tf_tt), ",".join(tf_st), tf_email, 
                               middle_st=stations[tf_m])
                    st.success("✅ 中转任务已保存！后台将自动轮询双程票。")
                    time.sleep(1)
                    st.rerun()

    # --- 我的任务列表 ---
    col_t1, col_t2 = st.columns([4, 1])
    with col_t1:
        st.markdown("### 📋 正在运行的任务")
    with col_t2:
        if st.button("🔄 刷新状态"):
            st.rerun()

    tasks = db.get_user_tasks(st.session_state.user)
    
    if not tasks:
        st.info("暂无任务，快去添加一个吧！")
    else:
        for task in tasks:
            # 解包任务元组
            # 兼容性处理：数据库可能有12或13个字段 (取决于 middle_station 是否在最后)
            # 假设顺序: id, user, f, t, date, tt, st, email, status, created, last_check, last_notify, [middle]
            t_id = task[0]
            f_st_code = task[2]
            t_st_code = task[3]
            date_str = task[4]
            seat_str = task[6]
            status = task[8]
            
            # 尝试获取 middle_station (假设它是第13个字段，索引12)
            middle_st_code = None
            if len(task) > 12:
                middle_st_code = task[12]

            # 车站代码转中文
            try:
                f_name = [k for k,v in stations.items() if v==f_st_code][0]
                t_name = [k for k,v in stations.items() if v==t_st_code][0]
                m_name = [k for k,v in stations.items() if v==middle_st_code][0] if middle_st_code else None
            except:
                f_name, t_name, m_name = f_st_code, t_st_code, middle_st_code

            status_text = "🟢 监控中" if status == 1 else ("🔴 已停止" if status == 0 else "🎉 已抢到")
            
            with st.container():
                col1, col2, col3, col4 = st.columns([3, 3, 2, 1])
                
                # 显示路线
                if m_name:
                    col1.markdown(f"**{f_name} ➝ <span style='color:#F2A626'>{m_name}</span> ➝ {t_name}**", unsafe_allow_html=True)
                    col1.caption("🔀 中转方案")
                else:
                    col1.markdown(f"**{f_name} ➝ {t_name}**")
                    col1.caption("➡️ 直达方案")

                col2.caption(f"📅 {date_str} | 🎯 {seat_str}")
                col3.markdown(f"{status_text}")
                if col4.button("🗑️ 删除", key=f"del_{t_id}"):
                    db.delete_task(t_id)
                    st.rerun()
                
                # --- 状态详情栏 ---
                # 解析时间字段
                # 假设 last_check 是第10个(index 10), last_notify 是第11个(index 11)
                # 再次强调：这里依赖数据库查询返回的顺序
                try:
                    l_check = task[10]
                    l_notify = task[11]
                    if isinstance(l_check, str): l_check = datetime.strptime(l_check, "%Y-%m-%d %H:%M:%S")
                    if isinstance(l_notify, str): l_notify = datetime.strptime(l_notify, "%Y-%m-%d %H:%M:%S")
                except:
                    l_check, l_notify = None, None

                # 计算状态
                now = datetime.now()
                info_msg = ""
                
                # 1. 冷却判断
                if l_notify and (now - l_notify < timedelta(hours=3)):
                    recover_time = l_notify + timedelta(hours=3)
                    info_msg = f"❄️ **已发现余票，暂停打扰** (冷却至 {recover_time.strftime('%H:%M')})"
                    st.warning(info_msg, icon="❄️")
                
                # 2. 常规轮询判断
                elif status == 1:
                    if not l_check:
                        st.info("⏳ **新任务加入队列，等待后台首次扫描...**", icon="🚀")
                    else:
                        next_run = l_check + timedelta(minutes=10) # 10分钟轮询间隔
                        # 如果下次运行时间已经过了，说明马上就要跑了
                        if next_run < now:
                            next_str = "马上执行"
                        else:
                            next_str = next_run.strftime('%H:%M:%S')
                        
                        st.caption(f"🕒 上次检查: {l_check.strftime('%H:%M:%S')} | 🔜 预计下次: **{next_str}**")
                
                st.divider()

if st.session_state.user:
    main_dashboard()
else:
    login_page()