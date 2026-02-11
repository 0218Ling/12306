import subprocess
import time
import sys
import os
import signal


def run_services():
    print("🚀 正在启动 12306 云监控服务...")

    # 获取当前 Python 解释器路径 (兼容 Windows/Linux)
    py_executable = sys.executable

    # 1. 启动 Streamlit 前台
    print("---------------------------------------------------------")
    print("👉 启动 Web 前台 (monitor_app.py)...")
    # 使用 sys.executable -m streamlit 确保使用同一个环境
    web_process = subprocess.Popen([
        py_executable, "-m", "streamlit", "run", "monitor_app.py",
        "--server.address", "0.0.0.0",
        "--server.port", "8501"
    ])

    # 2. 启动 后台 Worker
    print("👉 启动 后台守护进程 (backend_worker.py)...")
    # 使用 sys.executable 启动 worker
    worker_process = subprocess.Popen([py_executable, "backend_worker.py"])

    print("---------------------------------------------------------")
    print("✅ 服务已全部启动！")
    print("🌐 访问地址: http://localhost:8501")
    print("❌ 按 Ctrl+C 可停止所有服务")
    print("---------------------------------------------------------")

    try:
        while True:
            time.sleep(2)
            # 检查子进程状态
            if web_process.poll() is not None:
                print("⚠️ Streamlit 前台意外停止！日志请看 stdout")
                break
            if worker_process.poll() is not None:
                print("⚠️ Worker 后台意外停止！检查 backend_worker.py 是否有错")
                break

    except KeyboardInterrupt:
        print("\n🛑 收到停止信号...")

    finally:
        print("🧹 正在清理进程...")
        # 无论如何退出，都要清理子进程
        if web_process.poll() is None:
            web_process.terminate()
        if worker_process.poll() is None:
            worker_process.terminate()

        # 等待进程平稳退出
        try:
            web_process.wait(timeout=5)
            worker_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            web_process.kill()
            worker_process.kill()

        print("👋 服务已停止。")


if __name__ == "__main__":
    run_services()