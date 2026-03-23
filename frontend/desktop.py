import webview
import threading
import uvicorn
import time
import sys
import urllib.request

def start_api_server():
    try:
        # 🚀 關鍵修復：改用 uvicorn.Config 和字串載入 "app:app"
        # 這樣它就會知道自己在背景，不會去搶主執行緒的訊號控制權
        config = uvicorn.Config(
            "app:app", 
            host="127.0.0.1", 
            port=8000, 
            log_level="error" # 只顯示嚴重錯誤，保持背景乾淨
        )
        server = uvicorn.Server(config)
        server.run()
    except Exception as e:
        print(f"\n❌ [致命錯誤] FastAPI 伺服器啟動失敗: {e}")
        print("💡 可能是 port 8000 被剛剛沒關乾淨的終端機佔用了，請關閉其他 Python 視窗！\n")

if __name__ == '__main__':
    print("⚙️ 啟動 NextSPICE 核心引擎 (背景)...")
    
    # 1. 開啟背景執行緒跑 FastAPI
    server_thread = threading.Thread(target=start_api_server, daemon=True)
    server_thread.start()

    # 2. 智慧偵測：不斷 Ping 伺服器，直到它真的回傳網頁為止 (最多等 3 秒)
    print("⏳ 等待引擎連線...", end="", flush=True)
    server_ready = False
    for _ in range(30):
        try:
            urllib.request.urlopen("http://127.0.0.1:8000/")
            server_ready = True
            break
        except Exception:
            time.sleep(0.1)
            print(".", end="", flush=True)
    
    print() # 換行

    if not server_ready:
        print("❌ 伺服器沒有回應，啟動終止。請檢查上面的錯誤訊息。")
        sys.exit(1)

    print("✨ 引擎上線！召喚 NextSPICE 桌面視窗...")
    
    # 3. 確定伺服器活著，才建立桌面視窗
    window = webview.create_window(
        title='NextSPICE Industrial Studio', 
        url='http://127.0.0.1:8000',
        width=1280, 
        height=800,
        min_size=(800, 600),
        background_color='#1e1e1e'
    )

    webview.start()
    sys.exit()