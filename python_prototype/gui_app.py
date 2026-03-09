import tkinter as tk
from tkinter import scrolledtext, messagebox
import matplotlib.pyplot as plt
import sys
import os

# 自動修正路徑，確保能 import engine 內的模組
base_path = os.path.dirname(os.path.abspath(__file__))
if base_path not in sys.path:
    sys.path.append(base_path)

try:
    from engine.mna import Circuit, load_spice_netlist
    from engine.model import VoltageSource, Resistor, Diode
    import engine.linalg_core as la
except ImportError as e:
    print(f"錯誤：找不到 engine 相關模組。請確認資料夾結構正確。\n{e}")
    sys.exit(1)

class NextSpiceApp:
    def __init__(self, root):
        self.root = root
        self.root.title("NextSPICE v1.0 - 非線性電路模擬器")
        self.root.geometry("800x600")
        self.root.configure(bg="#2b2b2b")

        # 頂部標題
        title_label = tk.Label(
            root, text="NextSPICE EDA Console", 
            font=("Segoe UI", 16, "bold"), fg="#61afef", bg="#2b2b2b"
        )
        title_label.pack(pady=10)

        # 說明文字
        info_label = tk.Label(
            root, text="輸入 SPICE Netlist 並點擊 Run 進行 DC Sweep 模擬 (-10V to 10V)", 
            font=("Segoe UI", 9), fg="#abb2bf", bg="#2b2b2b"
        )
        info_label.pack()

        # Netlist 輸入區
        self.text_area = scrolledtext.ScrolledText(
            root, width=90, height=20, 
            font=("Consolas", 11), bg="#1e1e1e", fg="#dcdcdc",
            insertbackground="white", padx=10, pady=10
        )
        self.text_area.pack(padx=20, pady=10, expand=True, fill=tk.BOTH)
        
        # 預設橋式整流範例
        # 注意：V1 的數值會被 dc_sweep 覆蓋，所以寫 0 即可
        bridge_example = (
            "* NextSPICE 橋式整流測試 (Bridge Rectifier)\n"
            "V1 AC1 AC2 0\n"
            "D1 AC1 OUT_P\n"
            "D2 AC2 OUT_P\n"
            "D3 0 AC1\n"
            "D4 0 AC2\n"
            "RL OUT_P 0 1k\n"
            "* 提示：輸出節點請命名為 OUT_P 觀看全波效果"
        )
        self.text_area.insert(tk.INSERT, bridge_example)

        # 按鈕容器
        btn_frame = tk.Frame(root, bg="#2b2b2b")
        btn_frame.pack(pady=15)

        self.run_btn = tk.Button(
            btn_frame, text="▶ Run Simulation", command=self.run_simulation,
            bg="#98c379", fg="#282c34", font=("Segoe UI", 10, "bold"),
            padx=20, pady=5, relief=tk.FLAT
        )
        self.run_btn.grid(row=0, column=0, padx=10)

        self.clear_btn = tk.Button(
            btn_frame, text="Clear Netlist", command=lambda: self.text_area.delete(1.0, tk.END),
            bg="#e06c75", fg="white", font=("Segoe UI", 10),
            padx=15, pady=5, relief=tk.FLAT
        )
        self.clear_btn.grid(row=0, column=1, padx=10)

    def run_simulation(self):
        netlist = self.text_area.get(1.0, tk.END).strip()
        if not netlist:
            messagebox.showwarning("空清單", "請輸入 Netlist 內容！")
            return

        try:
            # 1. 初始化電路與解析
            ckt = Circuit()
            load_spice_netlist(netlist, ckt)
            
            # 2. 執行掃描 (模擬 AC 的變化過程)
            # 使用你自己寫的 la.arange
            start_v, stop_v, step_v = -10.0, 10.0, 0.2
            v_axis, data = ckt.dc_sweep("V1", start_v, stop_v, step_v)
            
            # 3. 繪圖
            plt.figure(num="NextSPICE 模擬結果", figsize=(10, 6))
            plt.clf() # 清除舊圖
            
            # 繪製輸入參考線 (Source)
            plt.plot(v_axis, v_axis, '--', label="Input Source (V1)", color='#56b6c2', alpha=0.6)
            
            # 自動尋找所有非 GND 節點並繪圖
            plotted_nodes = 0
            for node_name, node_id in ckt.node_map.items():
                if node_name in ["0", "GND"]:
                    continue
                
                # 提取該節點的所有電壓點
                v_node = [d[node_name] for d in data]
                plt.plot(v_axis, v_node, label=f"V({node_name})", linewidth=2)
                plotted_nodes += 1

            if plotted_nodes == 0:
                raise ValueError("電路中沒有可偵測的輸出節點。")

            # 4. 圖表美化
            plt.axhline(0, color='black', lw=1)
            plt.axvline(0, color='black', lw=1)
            plt.title("NextSPICE: Non-linear Circuit Analysis", fontsize=14)
            plt.xlabel("Input Voltage V1 (V)", fontsize=12)
            plt.ylabel("Output Voltage (V)", fontsize=12)
            plt.grid(True, linestyle=':', alpha=0.7)
            plt.legend(loc='best')
            
            # 彈出視窗
            plt.show()

        except Exception as e:
            messagebox.showerror("模擬失敗", f"發生錯誤：\n{str(e)}")

if __name__ == "__main__":
    root = tk.Tk()
    app = NextSpiceApp(root)
    root.mainloop()