import psutil
import os

def kill_process_on_port(port):
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            for conn in proc.connections(kind='inet'):
                if conn.laddr.port == port:
                    print(f"终止进程 {proc.info['name']} (PID: {proc.info['pid']}) 在端口: {port}")
                    proc.terminate() # 或者用 proc.kill() 强制杀死
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

# 使用示例
kill_process_on_port(8000)  # 通常是 Django
kill_process_on_port(5000)  # 通常是 Flask
kill_process_on_port(3000)  # 通常是 React/前端