import sys
import os
import math
import matplotlib.pyplot as plt

# 1. 環境設定：確保能抓到 engine
base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if base_path not in sys.path:
    sys.path.append(base_path)

from engine.mna import Circuit
from engine.model import VoltageSource, Resistor, Diode
import engine.linalg_core as la

# 2. 初始化電路
ckt = Circuit()
n_ac1 = ckt.get_node("AC1")
n_ac2 = ckt.get_node("AC2")
n_out_p = ckt.get_node("OUT_P")
n_gnd = 0  # 參考地

# 3. 建立電壓源 (橫跨在 AC1 與 AC2 之間，模擬浮動 AC 輸入)
v_src = VoltageSource(n_ac1, n_ac2, 0.0) 
ckt.add_component(v_src)

# 4. 建立橋式結構 (四顆二極體)
# 當 AC1 > AC2: 電流經 D1 -> OUT_P -> RL -> GND -> D4 -> AC2
# 當 AC2 > AC1: 電流經 D2 -> OUT_P -> RL -> GND -> D3 -> AC1
ckt.add_component(Diode(n_ac1, n_out_p)) # D1
ckt.add_component(Diode(n_ac2, n_out_p)) # D2
ckt.add_component(Diode(n_gnd, n_ac1))   # D3
ckt.add_component(Diode(n_gnd, n_ac2))   # D4

# 5. 建立負載
ckt.add_component(Resistor(n_out_p, n_gnd, 1000)) # 1k RL

# 6. 核心：加入高阻值參考電阻 (防止矩陣奇異，這是 EDA 的商業秘訣)
ckt.add_component(Resistor(n_ac1, n_gnd, 1e8)) # 100Meg to GND
ckt.add_component(Resistor(n_ac2, n_gnd, 1e8)) # 100Meg to GND

# 7. 執行模擬：DC Sweep 模擬一個完整的正弦波區間
v_input = la.arange(-10.0, 10.0, 0.2)
v_output = []

print("NextSPICE: 開始橋式全波整流模擬...")

for v in v_input:
    v_src.val = v
    try:
        # 內含牛頓迭代法的求解器
        sol = ckt.solve_dc() 
        v_output.append(sol["OUT_P"])
    except Exception as e:
        print(f"警告：在 {v}V 處發生錯誤 - {e}")
        v_output.append(0)

# 8. 繪圖視覺化
plt.figure(figsize=(10, 6))
plt.style.use('bmh') # 使用較具科技感的風格

# 繪製輸入與輸出
plt.plot(v_input, v_input, '--', label="Input Source (V1: AC1-AC2)", color='gray', alpha=0.6)
plt.plot(v_input, v_output, label="Full-Wave Output (V_OUT_P)", linewidth=2.5, color='#e06c75')

# 標記物理特性
plt.axhline(0, color='black', lw=1)
plt.axvline(0, color='black', lw=1)
plt.title("NextSPICE v1.0: Full-Wave Bridge Rectifier Analysis", fontsize=14)
plt.xlabel("Input Voltage (V)", fontsize=12)
plt.ylabel("Output Voltage (V)", fontsize=12)
plt.grid(True, linestyle=':', alpha=0.7)
plt.legend()

print("模擬完成，正在彈出圖表...")
plt.show()