import webview
import threading
import uvicorn
import time
import sys
import urllib.request

def start_api_server():
    try:
        config = uvicorn.Config(
            "app1:app",
            host="127.0.0.1",
            port=8000,
            log_level="error"
        )
        server = uvicorn.Server(config)
        server.run()
    except Exception as e:
        print(f"\n[ERR] FastAPI 伺服器啟動失敗: {e}")
        print("可能是 port 8000 被佔用，請關閉其他 Python 視窗！\n")

if __name__ == '__main__':
    print("啟動 NextSPICE v2 核心引擎 (背景)...")

    server_thread = threading.Thread(target=start_api_server, daemon=True)
    server_thread.start()

    print("等待引擎連線...", end="", flush=True)
    server_ready = False
    for _ in range(30):
        try:
            urllib.request.urlopen("http://127.0.0.1:8000/")
            server_ready = True
            break
        except Exception:
            time.sleep(0.1)
            print(".", end="", flush=True)

    print()

    if not server_ready:
        print("伺服器沒有回應，啟動終止。請檢查上面的錯誤訊息。")
        sys.exit(1)

    print("引擎上線！召喚 NextSPICE 桌面視窗...")

    window = webview.create_window(
        title='NextSPICE Industrial Studio v2',
        url='http://127.0.0.1:8000',
        width=1280,
        height=800,
        min_size=(800, 600),
        background_color='#1e1e1e'
    )

    webview.start()
    sys.exit()
