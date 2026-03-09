import sys
import os
import math
import matplotlib.pyplot as plt

# 確保路徑正確
base_path = os.path.dirname(os.path.abspath(__file__))
if base_path not in sys.path:
    sys.path.append(base_path)

from engine.mna import Circuit
from engine.model import VoltageSource, Resistor, Diode, Capacitor
import engine.linalg_core as la

def run_demo():
    ckt = Circuit()
    
    # 建立節點
    n_ac1 = ckt.get_node("AC1")
    n_ac2 = ckt.get_node("AC2")
    n_out = ckt.get_node("OUT")
    n_gnd = 0

    # 1. 建立交流電壓源: 10V Peak, 60Hz
    # V(t) = 10 * sin(2 * pi * 60 * t)
    v_func = lambda t: 10 * math.sin(2 * math.pi * 60 * t)
    v_src = VoltageSource(n_ac1, n_ac2, func=v_func)
    ckt.add_component(v_src)

    # 2. 橋式整流結構
    ckt.add_component(Diode(n_ac1, n_out)) # D1
    ckt.add_component(Diode(n_ac2, n_out)) # D2
    ckt.add_component(Diode(n_gnd, n_ac1)) # D3
    ckt.add_component(Diode(n_gnd, n_ac2)) # D4

    # 3. 濾波電容 (100uF) 與 負載電阻 (1k)
    ckt.add_component(Capacitor(n_out, n_gnd, 100e-6))
    ckt.add_component(Resistor(n_out, n_gnd, 1000))

    # 4. 加入參考地電阻防止矩陣奇異
    ckt.add_component(Resistor(n_ac1, n_gnd, 1e8))
    ckt.add_component(Resistor(n_ac2, n_gnd, 1e8))

    # 5. 執行暫態分析
    # 模擬 0.05 秒 (約三個週期)，步長 0.1ms
    t_stop = 0.05
    dt = 0.0001
    t_axis, results = ckt.solve_transient(t_stop, dt)

    # 提取數據
    v_in = [v_func(t) for t in t_axis]
    v_rect = [sol["OUT"] for sol in results]

    # 6. 繪圖
    plt.figure(figsize=(12, 6))
    plt.style.use('bmh') # 科技感風格
    
    plt.plot(t_axis, v_in, '--', label="Input AC (60Hz)", color='gray', alpha=0.5)
    plt.plot(t_axis, v_rect, label="Filtered DC (100uF Cap)", linewidth=2.5, color='#e06c75')

    plt.title("NextSPICE: Full-Bridge Rectifier with Capacitor Filtering", fontsize=14)
    plt.xlabel("Time (s)", fontsize=12)
    plt.ylabel("Voltage (V)", fontsize=12)
    plt.legend(loc='upper right')
    plt.grid(True, linestyle=':', alpha=0.7)
    
    print("NextSPICE: 模擬成功！正在顯示濾波波形...")
    plt.show()

if __name__ == "__main__":
    run_demo()