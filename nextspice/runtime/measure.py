# nextspice/runtime/measure.py
import numpy as np
import math
from scipy.interpolate import interp1d

class PostProcessor:
    """
    NextSPICE 後處理引擎
    專門處理 .MEASURE, .FOUR 等基於 raw_data 的數據分析。
    """
    def __init__(self, circuit_json, raw_data, log_callback):
        self.circuit_json = circuit_json
        self.raw_data = raw_data
        self.log = log_callback  # 呼叫 runner 傳進來的 log 函數
        self.results = {}        # 存放算出來的數據，最後還給 runner

    def run_all(self):
        """執行所有後處理分析"""
        self.evaluate_measures()
        self.evaluate_fourier()
        return self.results

    def safe_num(self, val):
        try:
            v = float(val)
            return 0.0 if math.isnan(v) or math.isinf(v) else v
        except:
            return 0.0

    def evaluate_measures(self):
        measures = self.circuit_json.get("measures", [])
        if not measures:
            return

        self.log("--- .MEASURE Results ---")
        for m in measures:
            atype = m.get("analysis_type", "tran").lower()
            name = m.get("name", "UNNAMED").upper()
            op = m.get("operation", "MAX").upper()
            target = m.get("target", "").upper()

            if atype == 'tran' and self.raw_data.get("tran"):
                data = self.raw_data["tran"][0]["data"] 
                if not data or target not in data[0]:
                    self.log(f"[ERR] .MEASURE 無法找到目標變數 {target}")
                    continue
                
                vals = [step[target] for step in data]
                res_val = 0.0
                
                try:
                    if op == "MAX": res_val = max(vals)
                    elif op == "MIN": res_val = min(vals)
                    elif op == "PP": res_val = max(vals) - min(vals)
                    elif op == "AVG": res_val = sum(vals) / len(vals)
                    elif op == "RMS": res_val = math.sqrt(sum(v**2 for v in vals) / len(vals))
                    else:
                        self.log(f"[WARN] 尚未支援的測量操作: {op}")
                        continue
                        
                    self.log(f"{name} ({op} of {target}): {res_val:.5e}")
                    self.results[f"MEAS: {name}"] = self.safe_num(res_val)
                    
                except Exception as e:
                    self.log(f"[ERR] 計算測量 {name} 失敗: {str(e)}")

    def evaluate_fourier(self):
        fourier_cmds = self.circuit_json.get("fourier", [])
        if not fourier_cmds or not self.raw_data.get("tran"):
            return

        self.log("--- .FOUR Fourier Analysis ---")
        data = self.raw_data["tran"][0]["data"]
        t_vals = np.array([step["time"] for step in data])
        
        if len(t_vals) < 10:
            self.log("[ERR] 暫態資料點過少，無法執行傅立葉轉換。")
            return

        t_start, t_stop = t_vals[0], t_vals[-1]
        sim_time = t_stop - t_start
        num_points = max(len(t_vals), 4096)
        t_uniform = np.linspace(t_start, t_stop, num_points)
        dt = t_uniform[1] - t_uniform[0]

        for cmd in fourier_cmds:
            fund_freq = float(cmd.get("freq", 1000.0))
            targets = cmd.get("targets", [])
            
            if 1.0 / sim_time > fund_freq:
                self.log(f"[WARN] 模擬總時間太短，解析度不足以捕捉基頻 ({fund_freq}Hz)！")

            for target in targets:
                if target not in data[0]:
                    self.log(f"[ERR] .FOUR 找不到目標變數 {target}")
                    continue

                y_vals = np.array([step[target] for step in data])
                
                # 1. 插值重取樣
                interp_func = interp1d(t_vals, y_vals, kind='cubic', fill_value="extrapolate")
                y_uniform = interp_func(t_uniform)

                # 2. FFT 計算
                fft_y = np.fft.rfft(y_uniform)
                fft_f = np.fft.rfftfreq(num_points, d=dt)
                
                mag = np.abs(fft_y) * 2.0 / num_points
                mag[0] /= 2.0 
                
                self.log(f"Fourier analysis for {target}:")
                self.log(f"  DC component = {mag[0]:.5e}")
                
                harmonics = []
                for i in range(1, 10):
                    target_f = fund_freq * i
                    idx = (np.abs(fft_f - target_f)).argmin()
                    h_mag = mag[idx]
                    phase = np.angle(fft_y[idx], deg=True)
                    harmonics.append((target_f, h_mag, phase))
                    
                    norm_mag = h_mag / harmonics[0][1] if harmonics[0][1] != 0 else 0
                    self.log(f"  Harmonic {i:<2}: {target_f:<8.1f}Hz | Mag: {h_mag:.5e} | Norm: {norm_mag:.5f} | Phase: {phase:>7.2f}°")

                # 3. THD 計算
                v1 = harmonics[0][1]
                if v1 > 0:
                    sum_sq = sum([h[1]**2 for h in harmonics[1:]])
                    thd = (math.sqrt(sum_sq) / v1) * 100.0
                    self.log(f"  Total Harmonic Distortion (THD) = {thd:.4f} %")
                    self.results[f"THD({target})"] = self.safe_num(thd)
                else:
                    self.log("  [WARN] 基頻振幅過小，無法計算 THD。")