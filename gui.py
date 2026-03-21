import os
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext
import numpy as np

# 引入 Matplotlib 內嵌 Tkinter 的套件
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

# 確保引用路徑正確
from nextspice.core.compiler import SpiceParser
from nextspice.core.circuit import Circuit
from nextspice.engine.solver import Simulator

# 設定 Matplotlib 暗色主題以搭配 UI
plt.style.use('dark_background')

class NextSpiceGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("NextSPICE Industrial Simulator v0.5 (Time-Domain Edition)")
        self.root.geometry("1200x700")
        self.root.configure(bg="#1e1e1e")

        # --- 頂部控制列 ---
        frame_top = tk.Frame(root, pady=10, padx=10, bg="#2d2d2d")
        frame_top.pack(fill=tk.X)
        
        tk.Label(frame_top, text="Netlist File:", font=("Consolas", 10, "bold"), bg="#2d2d2d", fg="#ffffff").pack(side=tk.LEFT)
        self.file_path_var = tk.StringVar()
        self.entry_path = tk.Entry(frame_top, textvariable=self.file_path_var, width=60, font=("Consolas", 10), bg="#1e1e1e", fg="#ffffff", insertbackground="white")
        self.entry_path.pack(side=tk.LEFT, padx=10)
        
        btn_style = {"font": ("Consolas", 10, "bold"), "relief": tk.FLAT, "padx": 10, "pady": 2}
        tk.Button(frame_top, text="📂 Browse", bg="#555555", fg="white", command=self.browse_file, **btn_style).pack(side=tk.LEFT, padx=5)
        tk.Button(frame_top, text="⚡ RUN SIM", bg="#007acc", fg="white", command=self.run_simulation, **btn_style).pack(side=tk.RIGHT, padx=5)

        # --- 內容區分屏 (左右) ---
        pane = tk.PanedWindow(root, orient=tk.HORIZONTAL, bg="#1e1e1e", sashwidth=5, sashrelief=tk.RAISED)
        pane.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # 左側：文字日誌區
        frame_log = tk.Frame(pane, bg="#1e1e1e")
        tk.Label(frame_log, text=">_ Simulation Console", font=("Consolas", 10, "bold"), bg="#1e1e1e", fg="#4CAF50").pack(anchor="w")
        self.text_out = scrolledtext.ScrolledText(frame_log, wrap=tk.WORD, font=("Consolas", 10), bg="#000000", fg="#D4D4D4", insertbackground="white")
        self.text_out.pack(fill=tk.BOTH, expand=True, pady=5)
        pane.add(frame_log, minsize=400)

        # 右側：Matplotlib 畫布區
        frame_plot = tk.Frame(pane, bg="#1e1e1e")
        tk.Label(frame_plot, text="📊 Waveform Viewer", font=("Consolas", 10, "bold"), bg="#1e1e1e", fg="#007acc").pack(anchor="w")
        
        self.fig = Figure(figsize=(6, 5), dpi=100)
        self.fig.patch.set_facecolor('#1e1e1e')
        self.canvas = FigureCanvasTkAgg(self.fig, master=frame_plot)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, pady=5)
        pane.add(frame_plot, minsize=500)

    def browse_file(self):
        filename = filedialog.askopenfilename(title="Select SPICE Netlist", filetypes=(("SPICE Files", "*.cir *.sp"), ("All Files", "*.*")))
        if filename: self.file_path_var.set(filename)

    def log(self, message, color="#D4D4D4"):
        self.text_out.insert(tk.END, message + "\n")
        self.text_out.see(tk.END)
        if color != "#D4D4D4":
            tag_name = f"color_{color.replace('#', '')}"
            self.text_out.tag_config(tag_name, foreground=color)
            last_line_index = self.text_out.index(tk.END + "-2c linestart")
            self.text_out.tag_add(tag_name, last_line_index, tk.END)

    def run_simulation(self):
        file_path = self.file_path_var.get()
        self.text_out.delete(1.0, tk.END)
        self.fig.clf() # 清空畫布
        self.canvas.draw()
        
        if not file_path or not os.path.exists(file_path):
            self.log("❌ ERROR: Please select a valid netlist file first.", "#FF5555")
            return

        self.log(f"🚀 Launching NextSPICE: {os.path.basename(file_path)}\n", "#4CAF50")

        try:
            # --- Phase 1 & 2: Compile & Build ---
            parser = SpiceParser(file_path=file_path)
            parsed_data = parser.compile()
            
            for d in parsed_data.get("diagnostics", []):
                sev = d['severity']
                c = "#FF5555" if sev == "ERROR" else "#FFAA00" if sev == "WARNING" else "#D4D4D4"
                self.log(f"[{sev}] Line {d.get('line', '?')}: {d['message']}", c)
                if sev == "ERROR": return self.log("❌ Compilation Failed.", "#FF5555")

            circuit = Circuit(name=os.path.basename(file_path))
            build_res = circuit.build_from_json(parsed_data["circuit"])
            if not build_res.success:
                for err in build_res.errors: self.log(f"[ERROR] {err}", "#FF5555")
                return self.log("❌ Circuit Build Failed.", "#FF5555")

            # --- Phase 3: Simulate & Plot ---
            simulator = Simulator(circuit)
            analyses = parsed_data["circuit"].get("analyses", [])
            if not analyses: return self.log("⚠️ No analysis directives (.OP, .AC, .TRAN) found.", "#FFAA00")

            for analysis in analyses:
                atype = analysis["type"]
                
                # ==== OP 分析 ====
                if atype == "op":
                    self.log("\n--- .OP Analysis ---", "#007acc")
                    res = simulator.solve_op()
                    if res.status == "SUCCESS":
                        report = simulator.get_full_report(res.x)
                        for name, val in report.items():
                            unit = "A" if name.startswith("I(") else "V"
                            self.log(f"{name:<10} | {val:>12.5e} {unit}")
                    else:
                        self.log(f"❌ OP Failed: {res.error_msg}", "#FF5555")

                # ==== AC 分析 ====
                elif atype == "ac":
                    self.log(f"\n--- .AC Analysis ({analysis['fstart']}Hz to {analysis['fstop']}Hz) ---", "#007acc")
                    ac_results = simulator.solve_ac(analysis['fstart'], analysis['fstop'], analysis['points'], analysis['sweep'])
                    
                    out_node = "OUT" if "OUT" in circuit.node_mgr.mapping else (circuit.node_mgr.get_name(1) if circuit.node_mgr.num_unknowns > 0 else None)
                    if not out_node:
                        self.log("⚠️ No valid probe node found for AC report.", "#FFAA00")
                        continue

                    out_idx = circuit.node_mgr.mapping.get(out_node) - 1
                    freqs, mags, phases = [], [], []
                    
                    for r in ac_results:
                        if r["status"] == "SUCCESS":
                            v_cplx = r["x"][out_idx]
                            f = r["freq"]
                            mag = 20 * np.log10(np.abs(v_cplx) + 1e-20)
                            phase = np.angle(v_cplx, deg=True)
                            
                            freqs.append(f)
                            mags.append(mag)
                            phases.append(phase)

                    if freqs:
                        self.log(f"  ✓ Processed {len(freqs)} frequency points successfully.")
                        ax1 = self.fig.add_subplot(211)
                        ax2 = self.fig.add_subplot(212, sharex=ax1)
                        
                        ax1.semilogx(freqs, mags, color='#00a8ff', linewidth=2)
                        ax1.set_ylabel('Magnitude (dB)', color='#D4D4D4')
                        ax1.set_title(f'AC Response @ V({out_node})', color='#ffffff')
                        ax1.grid(True, which="both", ls="--", alpha=0.3)
                        ax1.tick_params(colors='#D4D4D4')

                        ax2.semilogx(freqs, phases, color='#e84118', linewidth=2)
                        ax2.set_ylabel('Phase (deg)', color='#D4D4D4')
                        ax2.set_xlabel('Frequency (Hz)', color='#D4D4D4')
                        ax2.grid(True, which="both", ls="--", alpha=0.3)
                        ax2.tick_params(colors='#D4D4D4')
                        
                        self.fig.tight_layout()
                        self.fig.patch.set_facecolor('#1e1e1e')
                        for ax in [ax1, ax2]: ax.set_facecolor('#1e1e1e')
                        self.canvas.draw()

                # ==== TRAN 分析 (全新時域繪圖引擎) ====
                elif atype == "tran":
                    tstep, tstop = analysis['tstep'], analysis['tstop']
                    self.log(f"\n--- .TRAN Analysis (0 to {tstop*1000:.2f} ms) ---", "#007acc")
                    
                    tran_results = simulator.solve_tran(tstep, tstop)
                    
                    times = []
                    v_in_data = []
                    v_out_data = []
                    
                    in_idx = circuit.node_mgr.mapping.get("IN")
                    in_idx = in_idx - 1 if in_idx else None
                    
                    out_node = "OUT" if "OUT" in circuit.node_mgr.mapping else (circuit.node_mgr.get_name(1) if circuit.node_mgr.num_unknowns > 0 else None)
                    out_idx = circuit.node_mgr.mapping.get(out_node) - 1 if out_node else None

                    if out_idx is not None:
                        for r in tran_results:
                            if r["status"] == "SUCCESS":
                                t = r["time"]
                                x_vec = r["x"]
                                times.append(t * 1000) # 轉成 ms 比較好看
                                v_out_data.append(x_vec[out_idx])
                                if in_idx is not None:
                                    v_in_data.append(x_vec[in_idx])
                        
                        self.log(f"  ✓ Processed {len(times)} time steps successfully.")
                        
                        if times:
                            ax = self.fig.add_subplot(111)
                            
                            # 畫輸入方波 (綠色虛線)
                            if v_in_data:
                                ax.plot(times, v_in_data, color='#4CAF50', linestyle='--', linewidth=1.5, label='V(IN) Pulse')
                                
                            # 畫輸出響應 (科技藍實線)
                            ax.plot(times, v_out_data, color='#00a8ff', linewidth=2, label=f'V({out_node}) Response')
                            
                            ax.set_ylabel('Voltage (V)', color='#D4D4D4')
                            ax.set_xlabel('Time (ms)', color='#D4D4D4')
                            ax.set_title('Transient Response', color='#ffffff')
                            ax.grid(True, which="both", ls="--", alpha=0.3)
                            ax.tick_params(colors='#D4D4D4')
                            ax.legend(facecolor='#1e1e1e', edgecolor='#D4D4D4', labelcolor='#ffffff')
                            
                            self.fig.tight_layout()
                            self.fig.patch.set_facecolor('#1e1e1e')
                            ax.set_facecolor('#1e1e1e')
                            self.canvas.draw()

# ==== DC Sweep 分析 ====
                elif atype == "dc":
                    src, start, stop, step = analysis['source'], analysis['start'], analysis['stop'], analysis['step']
                    self.log(f"\n--- .DC Sweep ({src} from {start}V to {stop}V) ---", "#007acc")
                    
                    # 呼叫 Solver 執行掃描
                    dc_results = simulator.solve_dc_sweep(src, start, stop, step)
                    
                    if not dc_results or dc_results[0].get("status") == "ERROR":
                        self.log(f"❌ DC Sweep Failed: {dc_results[0].get('msg', 'Unknown Error')}", "#FF5555")
                        continue

                    v_in_data = []
                    v_out_data = []
                    
                    # 智慧抓取觀察節點 (Lv3_1 的分壓點是 MID)
                    out_node = "MID" if "MID" in circuit.node_mgr.mapping else (
                               "OUT" if "OUT" in circuit.node_mgr.mapping else 
                               (circuit.node_mgr.get_name(1) if circuit.node_mgr.num_unknowns > 0 else None))
                    
                    out_idx = circuit.node_mgr.mapping.get(out_node) - 1 if out_node else None

                    if out_idx is not None:
                        for r in dc_results:
                            res_obj = r["result"]
                            if res_obj.status == "SUCCESS":
                                v_in_data.append(r["v_in"])
                                v_out_data.append(res_obj.x[out_idx])
                                
                        self.log(f"  ✓ Processed {len(v_in_data)} sweep points successfully.")
                        
                        # 繪製 DC 轉換特性曲線 (DC Transfer Characteristic)
                        if v_in_data:
                            ax = self.fig.add_subplot(111)
                            
                            # 畫出輸入 vs 輸出的直線/曲線
                            ax.plot(v_in_data, v_out_data, color='#e84118', linewidth=2, marker='o', label=f'V({out_node})')
                            
                            ax.set_ylabel('Voltage (V)', color='#D4D4D4')
                            ax.set_xlabel(f'Sweep {src} (V)', color='#D4D4D4')
                            ax.set_title(f'DC Transfer Characteristic', color='#ffffff')
                            ax.grid(True, which="both", ls="--", alpha=0.3)
                            ax.tick_params(colors='#D4D4D4')
                            ax.legend(facecolor='#1e1e1e', edgecolor='#D4D4D4', labelcolor='#ffffff')
                            
                            self.fig.tight_layout()
                            self.fig.patch.set_facecolor('#1e1e1e')
                            ax.set_facecolor('#1e1e1e')
                            self.canvas.draw()
                    else:
                        self.log("  ⚠️ No valid probe node found for TRAN report.", "#FFAA00")

        except Exception as e:
            self.log(f"\n❌ UNEXPECTED CRASH: {str(e)}", "#FF5555")

if __name__ == "__main__":
    root = tk.Tk()
    app = NextSpiceGUI(root)
    root.mainloop()