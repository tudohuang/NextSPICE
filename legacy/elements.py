import numpy as np
import math
import cmath
import re
from nextspice.utils.unit_conv import UnitConverter as unit_conv

# --- 🚀 共用的波形計算核心 ---
def eval_source_waveform(tran_str, dc_value, t):
    """根據當下時間 t，計算時域波形的瞬間數值 (電壓或電流共用)"""
    if not tran_str:
        return dc_value

    tran_upper = tran_str.upper()
    
    match = re.search(r'\((.*?)\)', tran_upper)
    if not match:
        return dc_value
        
    raw_args = match.group(1).replace(',', ' ').split()
    args = [unit_conv.parse(x) for x in raw_args if x.strip()]

    # === 1. 正弦波 SIN(VO VA FREQ TD THETA) ===
    if tran_upper.startswith("SIN"):
        vo = args[0] if len(args) > 0 else 0.0       # DC 偏移量
        va = args[1] if len(args) > 1 else 0.0       # 振幅
        freq = args[2] if len(args) > 2 else 0.0     # 頻率
        td = args[3] if len(args) > 3 else 0.0       # 延遲時間
        theta = args[4] if len(args) > 4 else 0.0    # 阻尼系數
        
        if t < td:
            return vo
        else:
            return vo + va * math.exp(-theta * (t - td)) * math.sin(2 * math.pi * freq * (t - td))

    # === 2. 脈衝方波 PULSE(V1 V2 TD TR TF PW PER) ===
    elif tran_upper.startswith("PULSE"):
        v1 = args[0] if len(args) > 0 else 0.0       # 初始值
        v2 = args[1] if len(args) > 1 else 0.0       # 脈衝值
        td = args[2] if len(args) > 2 else 0.0       # 延遲時間
        tr = args[3] if len(args) > 3 else 0.0       # 上升時間
        tf = args[4] if len(args) > 4 else 0.0       # 下降時間
        pw = args[5] if len(args) > 5 else 1.0       # 脈衝寬度
        per = args[6] if len(args) > 6 else 1.0      # 週期

        if t < td:
            return v1

        t_cycle = (t - td) % per if per > 0 else (t - td)

        if t_cycle < tr:
            return v1 + (v2 - v1) * (t_cycle / tr) if tr > 0 else v2
        elif t_cycle < tr + pw:
            return v2
        elif t_cycle < tr + pw + tf:
            return v2 - (v2 - v1) * ((t_cycle - tr - pw) / tf) if tf > 0 else v1
        else:
            return v1

    # 🚀 === 3. 任意分段線性波形 PWL(T1 V1 T2 V2 T3 V3 ...) ===
    elif tran_upper.startswith("PWL"):
        # 至少要有兩個數字才構成一個座標點
        if len(args) < 2:
            return dc_value

        # 將一維陣列轉換為 (時間, 電壓/電流) 座標對陣列
        pts = [(args[i], args[i+1]) for i in range(0, len(args)-1, 2)]
        
        if not pts:
            return dc_value

        # 狀態 1：時間還沒到第一個點，保持第一個點的數值
        if t <= pts[0][0]:
            return pts[0][1]
            
        # 狀態 2：時間已經超過最後一個點，保持最後一個點的數值
        if t >= pts[-1][0]:
            return pts[-1][1]
            
        # 狀態 3：時間落在中間，尋找對應的區間進行「線性內插」
        for i in range(len(pts) - 1):
            t1, v1 = pts[i]
            t2, v2 = pts[i+1]
            
            if t1 <= t <= t2:
                # 防呆：如果兩個點時間一樣 (垂直線)，直接回傳後面的值避免除以零
                if t2 == t1:
                    return v2
                # 線性內插公式：V(t) = V1 + (V2 - V1) * (t - t1) / (t2 - t1)
                return v1 + (v2 - v1) * (t - t1) / (t2 - t1)

    return dc_value

# ==============================================================

class BaseElement:
    def __init__(self, name):
        self.name = name
        self.extra_vars = 0

    def stamp(self, A, b, extra_idx=None, ctx=None):
        raise NotImplementedError

class Resistor(BaseElement):
    def __init__(self, name, n1, n2, value):
        super().__init__(name)
        self.n1, self.n2 = n1, n2
        self.value = float(value)
        # 🚀 嚴格防呆：禁止 0 或負電阻 (除非未來引擎支援負阻抗)
        if self.value <= 0:
            raise ValueError(f"Resistor {self.name} has invalid value {self.value}. Value must be > 0.")

    def stamp(self, A, b, extra_idx=None, ctx=None):
        g = 1.0 / self.value # 🚀 移除了 1e-30 的掩耳盜鈴
        for i, j in [(self.n1, self.n1), (self.n2, self.n2)]:
            if i > 0 and j > 0: A[i-1, j-1] += g
        for i, j in [(self.n1, self.n2), (self.n2, self.n1)]:
            if i > 0 and j > 0: A[i-1, j-1] -= g


class VoltageSource(BaseElement):
    def __init__(self, name, n1, n2, dc_value=0.0, ac_mag=None, ac_phase=0.0, tran=None):
        super().__init__(name)
        self.n1, self.n2 = n1, n2
        self.dc_value = float(dc_value) if dc_value is not None else 0.0
        self.ac_mag = float(ac_mag) if ac_mag is not None else 0.0
        self.ac_phase = float(ac_phase) if ac_phase is not None else 0.0
        self.tran = tran
        self.extra_vars = 1

    def _eval_tran_voltage(self, t):
        # 🚀 呼叫共用函數
        return eval_source_waveform(self.tran, self.dc_value, t)

    def stamp(self, A, b, extra_idx, ctx=None):
        if self.n1 > 0:
            A[self.n1-1, extra_idx] += 1.0
            A[extra_idx, self.n1-1] += 1.0
        if self.n2 > 0:
            A[self.n2-1, extra_idx] -= 1.0
            A[extra_idx, self.n2-1] -= 1.0
            
        mode = ctx.get('mode', 'op') if ctx else 'op'
            
        if mode == 'ac':
            phase_rad = math.radians(self.ac_phase)
            b[extra_idx] = self.ac_mag * cmath.exp(1j * phase_rad)
        elif mode == 'tran':
            t = ctx.get('t', 0.0)
            b[extra_idx] = self._eval_tran_voltage(t)
        else:
            b[extra_idx] = self.dc_value


class CurrentSource(BaseElement):
    def __init__(self, name, n1, n2, dc_value=0.0, ac_mag=None, ac_phase=0.0, tran=None):
        super().__init__(name)
        self.n1, self.n2 = n1, n2
        self.dc_value = float(dc_value) if dc_value is not None else 0.0
        self.ac_mag = float(ac_mag) if ac_mag is not None else 0.0
        self.ac_phase = float(ac_phase) if ac_phase is not None else 0.0
        self.tran = tran # 🚀 補齊 tran 屬性

    def _eval_tran_current(self, t):
        # 🚀 呼叫共用函數，電流源現在也有脈衝和正弦波能力了！
        return eval_source_waveform(self.tran, self.dc_value, t)

    def stamp(self, A, b, extra_idx=None, ctx=None):
        mode = ctx.get('mode', 'op') if ctx else 'op'
        
        # 🚀 統一介面契約：不再用 'freq' in ctx 當作判斷依據
        if mode == 'ac':
            phase_rad = math.radians(self.ac_phase)
            val = self.ac_mag * cmath.exp(1j * phase_rad)
        elif mode == 'tran':
            t = ctx.get('t', 0.0)
            val = self._eval_tran_current(t)
        else:
            val = self.dc_value

        if self.n1 > 0: b[self.n1-1] -= val
        if self.n2 > 0: b[self.n2-1] += val



class MutualInductance(BaseElement):
    def __init__(self, name, l1_obj, l2_obj, k_value):
        super().__init__(name)
        self.l1_obj = l1_obj
        self.l2_obj = l2_obj
        self.k = float(k_value)
        if not (-1.0 <= self.k <= 1.0):
            raise ValueError(f"Coupling coefficient k for {self.name} must be between -1 and 1.")
        self.extra_vars = 0 
        self.M = self.k * math.sqrt(self.l1_obj.value * self.l2_obj.value)

    def stamp(self, A, b, extra_idx=None, ctx=None):
        extra_map = ctx.get('extra_map', {})
        idx1 = extra_map.get(self.l1_obj)
        idx2 = extra_map.get(self.l2_obj)

        if idx1 is None or idx2 is None:
            return

        mode = ctx.get('mode', 'op')

        if mode == 'ac':
            freq = ctx.get('freq', 1.0)
            omega = 2.0 * math.pi * freq
            zm = complex(0, omega * self.M)
            A[idx1, idx2] -= zm
            A[idx2, idx1] -= zm

        elif mode == 'tran':
            dt = ctx.get('dt', 1e-9)
            rm = self.M / dt
            A[idx1, idx2] -= rm
            A[idx2, idx1] -= rm
            b[idx1] += -rm * self.l2_obj.i_prev
            b[idx2] += -rm * self.l1_obj.i_prev
        else:
            pass


class VCVS(BaseElement):
    def __init__(self, name, np, nn, cp, cn, gain):
        super().__init__(name)
        self.n_out_p, self.n_out_n = np, nn
        self.n_in_p, self.n_in_n = cp, cn
        self.gain = float(gain)
        self.extra_vars = 1

    def stamp(self, A, b, extra_idx, ctx=None):
        if self.n_out_p > 0:
            A[self.n_out_p-1, extra_idx] += 1.0
            A[extra_idx, self.n_out_p-1] += 1.0
        if self.n_out_n > 0:
            A[self.n_out_n-1, extra_idx] -= 1.0
            A[extra_idx, self.n_out_n-1] -= 1.0
        if self.n_in_p > 0: A[extra_idx, self.n_in_p-1] -= self.gain
        if self.n_in_n > 0: A[extra_idx, self.n_in_n-1] += self.gain


class VCCS(BaseElement):
    def __init__(self, name, np, nn, cp, cn, transconductance):
        super().__init__(name)
        self.np, self.nn = np, nn
        self.cp, self.cn = cp, cn
        self.g = float(transconductance)

    def stamp(self, A, b, extra_idx=None, ctx=None):
        if self.np > 0 and self.cp > 0: A[self.np-1, self.cp-1] += self.g
        if self.np > 0 and self.cn > 0: A[self.np-1, self.cn-1] -= self.g
        if self.nn > 0 and self.cp > 0: A[self.nn-1, self.cp-1] -= self.g
        if self.nn > 0 and self.cn > 0: A[self.nn-1, self.cn-1] += self.g


class CCVS(BaseElement):
    def __init__(self, name, np, nn, ctrl_source, transresistance):
        super().__init__(name)
        self.np, self.nn = np, nn
        self.ctrl_source = ctrl_source.upper() 
        self.rm = float(transresistance)
        self.extra_vars = 1

    def stamp(self, A, b, extra_idx, ctx=None):
        ctrl_idx = ctx.get('extra_by_name', {}).get(self.ctrl_source)
        if ctrl_idx is None:
            raise ValueError(f"Controlling source '{self.ctrl_source}' not found for {self.name}")

        if self.np > 0:
            A[self.np-1, extra_idx] += 1.0
            A[extra_idx, self.np-1] += 1.0
        if self.nn > 0:
            A[self.nn-1, extra_idx] -= 1.0
            A[extra_idx, self.nn-1] -= 1.0
        
        A[extra_idx, ctrl_idx] -= self.rm


class CCCS(BaseElement):
    def __init__(self, name, np, nn, ctrl_source, gain):
        super().__init__(name)
        self.np, self.nn = np, nn
        self.ctrl_source = ctrl_source.upper()
        self.gain = float(gain)

    def stamp(self, A, b, extra_idx=None, ctx=None):
        ctrl_idx = ctx.get('extra_by_name', {}).get(self.ctrl_source)
        if ctrl_idx is None:
            raise ValueError(f"Controlling source '{self.ctrl_source}' not found for {self.name}")
        
        if self.np > 0: A[self.np-1, ctrl_idx] += self.gain
        if self.nn > 0: A[self.nn-1, ctrl_idx] -= self.gain

class Diode(BaseElement):
    def __init__(self, name, n1, n2, is_sat=1e-14, n=1.0, temp=300.15):
        super().__init__(name)
        self.n1 = n1
        self.n2 = n2
        self.is_nonlinear = True  # 🚀 補回非線性標記！不然引擎不會呼叫 stamp_nonlinear
        
        self.is_sat = float(is_sat)
        self.n = float(n)
        self.temp = float(temp)
        
        k = 1.380649e-23
        q = 1.602176634e-19
        self.vt = (k * self.temp) / q
        self.v_prev = 0.0

    @property
    def vcrit(self):
        nVt = self.n * self.vt
        return nVt * math.log(nVt / (math.sqrt(2) * self.is_sat))

    def _adaptive_junction_clamp(self, v_new, v_old, vt, v_crit):
        delta = v_new - v_old
        two_vt = 2.0 * vt
        if v_new > v_crit and abs(delta) > two_vt:
            if v_old > 0:
                scaled = delta / vt
                if scaled > 0:
                    v_new = v_old + vt * (2.0 + math.log(max(scaled - 2.0, 1e-30)))
                else:
                    v_new = v_old - vt * (2.0 + math.log(max(2.0 - scaled, 1e-30)))
            else:
                v_new = vt * math.log(max(v_new / vt, 1e-30))
        elif v_new < 0:
            floor = (-v_old - 1.0) if v_old > 0 else (2.0 * v_old - 1.0)
            v_new = max(v_new, floor)
        return v_new

    def stamp_nonlinear(self, x_old, A, b, extra_idx=None, ctx=None):
        v_p = x_old[self.n1 - 1] if self.n1 > 0 else 0.0
        v_n = x_old[self.n2 - 1] if self.n2 > 0 else 0.0
        vd_raw = v_p - v_n
        
        vd_safe = self._adaptive_junction_clamp(vd_raw, self.v_prev, self.vt * self.n, self.vcrit)
        self.v_prev = vd_safe 
        
        nVt = self.n * self.vt
        exp_term = math.exp(min(vd_safe / nVt, 100.0))
        
        id_val = self.is_sat * (exp_term - 1.0)
        gd_val = (self.is_sat / nVt) * exp_term
        
        G_MIN = 1e-12
        gd_val += G_MIN
        i_eq = id_val - gd_val * vd_safe + (G_MIN * vd_safe)
        
        if self.n1 > 0:
            A[self.n1 - 1, self.n1 - 1] += gd_val
            b[self.n1 - 1] -= i_eq
        if self.n2 > 0:
            A[self.n2 - 1, self.n2 - 1] += gd_val
            b[self.n2 - 1] += i_eq
        if self.n1 > 0 and self.n2 > 0:
            A[self.n1 - 1, self.n2 - 1] -= gd_val
            A[self.n2 - 1, self.n1 - 1] -= gd_val



class Capacitor(BaseElement):
    def __init__(self, name, n1, n2, value):
        super().__init__(name)
        self.n1 = n1
        self.n2 = n2
        self.value = float(value)
        self.v_prev = 0.0
        self.i_prev = 0.0

    def stamp(self, A, b, extra_idx=None, ctx=None):
        mode = ctx.get('mode', 'op') if ctx else 'op'
        
        if mode in ('dc', 'op'):
            gmin = 1e-12
            if self.n1 > 0: A[self.n1 - 1, self.n1 - 1] += gmin
            if self.n2 > 0: A[self.n2 - 1, self.n2 - 1] += gmin
            if self.n1 > 0 and self.n2 > 0:
                A[self.n1 - 1, self.n2 - 1] -= gmin
                A[self.n2 - 1, self.n1 - 1] -= gmin
                
        # 🚀 就是這裡！被我手殘刪掉的 AC 複數阻抗蓋章！
        elif mode == 'ac':
            freq = ctx.get('freq', 1.0)
            omega = 2.0 * math.pi * freq
            y_c = complex(0, omega * self.value)  # Y = jwC
            if self.n1 > 0: A[self.n1 - 1, self.n1 - 1] += y_c
            if self.n2 > 0: A[self.n2 - 1, self.n2 - 1] += y_c
            if self.n1 > 0 and self.n2 > 0:
                A[self.n1 - 1, self.n2 - 1] -= y_c
                A[self.n2 - 1, self.n1 - 1] -= y_c
                
        elif mode == 'tran':
            dt = ctx.get('dt', 1e-9)
            method = ctx.get('integration', 'trapezoidal')

            if method == 'gear2':
                # BDF-2: g_eq = 3C/(2*dt), i_hist = C/dt * (4*v(n-1) - v(n-2))
                # 但 v(n-2) 儲存在 self.v_prev2
                g_eq = 1.5 * self.value / dt
                i_hist = self.value / dt * (2.0 * self.v_prev - 0.5 * getattr(self, 'v_prev2', self.v_prev))
            elif method == 'trapezoidal':
                g_eq = 2.0 * self.value / dt
                i_hist = g_eq * self.v_prev + self.i_prev
            else:  # backward euler
                g_eq = self.value / dt
                i_hist = g_eq * self.v_prev

            if self.n1 > 0:
                A[self.n1 - 1, self.n1 - 1] += g_eq
                b[self.n1 - 1] += i_hist
            if self.n2 > 0:
                A[self.n2 - 1, self.n2 - 1] += g_eq
                b[self.n2 - 1] -= i_hist
            if self.n1 > 0 and self.n2 > 0:
                A[self.n1 - 1, self.n2 - 1] -= g_eq
                A[self.n2 - 1, self.n1 - 1] -= g_eq

    def update_history(self, x, extra_idx=None, **kwargs):
        v_p = x[self.n1 - 1] if self.n1 > 0 else 0.0
        v_n = x[self.n2 - 1] if self.n2 > 0 else 0.0
        v_now = v_p - v_n
        dt = kwargs.get('dt', None)
        method = kwargs.get('integration', 'trapezoidal')

        self.v_prev2 = self.v_prev  # Gear-2 需要 t(n-2)

        if method == 'trapezoidal' and dt:
            g_eq = 2.0 * self.value / dt
            self.i_prev = g_eq * (v_now - self.v_prev) - self.i_prev
        self.v_prev = v_now


class Inductor(BaseElement):
    def __init__(self, name, n1, n2, value):
        super().__init__(name)
        self.n1 = n1
        self.n2 = n2
        self.value = float(value)
        self.i_prev = 0.0
        self.v_prev = 0.0
        self.extra_vars = 1

    def stamp(self, A, b, extra_idx=None, ctx=None):
        if extra_idx is None:
            raise ValueError(f"[{self.name}] 致命錯誤：沒有分配到 extra_idx！")
            
        mode = ctx.get('mode', 'op') if ctx else 'op'
        idx = extra_idx
        
        if mode in ('dc', 'op'):
            if self.n1 > 0:
                A[self.n1 - 1, idx] += 1.0
                A[idx, self.n1 - 1] += 1.0
            if self.n2 > 0:
                A[self.n2 - 1, idx] -= 1.0
                A[idx, self.n2 - 1] -= 1.0
            b[idx] = 0.0
            A[idx, idx] -= 1e-12
            
        # 🚀 這裡也是！被我手殘刪掉的 AC 複數阻抗蓋章！
        elif mode == 'ac':
            freq = ctx.get('freq', 1.0)
            omega = 2.0 * math.pi * freq
            z_l = complex(0, omega * self.value)  # Z = jwL
            
            if self.n1 > 0:
                A[self.n1 - 1, idx] += 1.0
                A[idx, self.n1 - 1] += 1.0
            if self.n2 > 0:
                A[self.n2 - 1, idx] -= 1.0
                A[idx, self.n2 - 1] -= 1.0
            A[idx, idx] -= z_l
            
        elif mode == 'tran':
            dt = ctx.get('dt', 1e-9)
            method = ctx.get('integration', 'trapezoidal')

            if method == 'gear2':
                # BDF-2: r_eq = 3L/(2*dt)
                r_eq = 1.5 * self.value / dt
                v_hist = self.value / dt * (2.0 * self.i_prev - 0.5 * getattr(self, 'i_prev2', self.i_prev))
            elif method == 'trapezoidal':
                r_eq = 2.0 * self.value / dt
                v_hist = r_eq * self.i_prev + self.v_prev
            else:  # backward euler
                r_eq = self.value / dt
                v_hist = r_eq * self.i_prev

            if self.n1 > 0:
                A[self.n1 - 1, idx] += 1.0
                A[idx, self.n1 - 1] += 1.0
            if self.n2 > 0:
                A[self.n2 - 1, idx] -= 1.0
                A[idx, self.n2 - 1] -= 1.0

            A[idx, idx] -= r_eq
            b[idx] = -v_hist

    def update_history(self, x, extra_idx=None, **kwargs):
        if extra_idx is not None:
            i_now = x[extra_idx]
        else:
            i_now = 0.0

        v_p = x[self.n1 - 1] if self.n1 > 0 else 0.0
        v_n = x[self.n2 - 1] if self.n2 > 0 else 0.0
        v_now = v_p - v_n

        dt = kwargs.get('dt', None)
        method = kwargs.get('integration', 'trapezoidal')

        self.i_prev2 = self.i_prev  # Gear-2 需要 t(n-2)

        if method == 'trapezoidal' and dt:
            self.v_prev = v_now

        self.i_prev = i_now

class BJT(BaseElement):
    def __init__(self, name, nc, nb, ne, bjt_type='NPN', is_sat=1e-14, bf=100.0, br=1.0, temp=300.15):
        super().__init__(name)
        self.nc = nc  # Collector
        self.nb = nb  # Base
        self.ne = ne  # Emitter
        self.is_nonlinear = True
        
        # 極性乘數：NPN 為 1.0, PNP 為 -1.0
        self.bjt_type = 1.0 if bjt_type.upper() == 'NPN' else -1.0

        self.is_sat = float(is_sat)
        self.bf = float(bf)  # 正向 Beta
        self.br = float(br)  # 逆向 Beta
        self.temp = float(temp)

        # 🚀 計算 Ebers-Moll 模型的 Alpha 參數
        self.af = self.bf / (self.bf + 1.0)
        self.ar = self.br / (self.br + 1.0)

        # 物理常數與熱電壓
        k = 1.380649e-23
        q = 1.602176634e-19
        self.vt = (k * self.temp) / q

        # 記憶體：用來做 Newton-Raphson 自適應阻尼
        self.vbe_prev = 0.0
        self.vbc_prev = 0.0

        # 預留 AC 小信號參數
        self.gf_ac = 0.0
        self.gr_ac = 0.0

    @property
    def vcrit_f(self):
        return self.vt * math.log(self.vt / (math.sqrt(2) * (self.is_sat / self.af)))

    @property
    def vcrit_r(self):
        return self.vt * math.log(self.vt / (math.sqrt(2) * (self.is_sat / self.ar)))

    def _adaptive_junction_clamp(self, v_new, v_old, vt, v_crit):
        """完美的 PN 結自適應阻尼器 (Diode 移植過來)"""
        delta = v_new - v_old
        two_vt = 2.0 * vt
        if v_new > v_crit and abs(delta) > two_vt:
            if v_old > 0:
                scaled = delta / vt
                if scaled > 0:
                    v_new = v_old + vt * (2.0 + math.log(max(scaled - 2.0, 1e-30)))
                else:
                    v_new = v_old - vt * (2.0 + math.log(max(2.0 - scaled, 1e-30)))
            else:
                v_new = vt * math.log(max(v_new / vt, 1e-30))
        elif v_new < 0:
            floor = (-v_old - 1.0) if v_old > 0 else (2.0 * v_old - 1.0)
            v_new = max(v_new, floor)
        return v_new

    def stamp_nonlinear(self, A, b, x_old, extra_idx=None, ctx=None):
            # 1. 取得當下疊代的節點電壓
        vc = x_old[self.nc - 1] if self.nc > 0 else 0.0
        vb = x_old[self.nb - 1] if self.nb > 0 else 0.0
        ve = x_old[self.ne - 1] if self.ne > 0 else 0.0

        # 2. 計算等效接面電壓 (考慮 NPN/PNP 極性)
        vbe_raw = self.bjt_type * (vb - ve)
        vbc_raw = self.bjt_type * (vb - vc)

        # 3. 過阻尼器，防止指數爆炸
        vbe_safe = self._adaptive_junction_clamp(vbe_raw, self.vbe_prev, self.vt, self.vcrit_f)
        vbc_safe = self._adaptive_junction_clamp(vbc_raw, self.vbc_prev, self.vt, self.vcrit_r)

        self.vbe_prev = vbe_safe
        self.vbc_prev = vbc_safe

        # 4. Ebers-Moll 電流與電導 (Jacobian 斜率)
        exp_f = math.exp(min(vbe_safe / self.vt, 100.0))
        exp_r = math.exp(min(vbc_safe / self.vt, 100.0))

        i_f = (self.is_sat / self.af) * (exp_f - 1.0)
        g_f = (self.is_sat / (self.af * self.vt)) * exp_f

        i_r = (self.is_sat / self.ar) * (exp_r - 1.0)
        g_r = (self.is_sat / (self.ar * self.vt)) * exp_r

        # 🛡️ GMIN 防呆魔法 (絕對不能省！)
        G_MIN = 1e-12
        g_f += G_MIN
        g_r += G_MIN

        self.gf_ac = g_f
        self.gr_ac = g_r

        # 5. 計算等效 Norton 電流源 (I_eq = I - G * V)
        ieq_f = i_f - g_f * vbe_safe
        ieq_r = i_r - g_r * vbc_safe

        # 計算端點注入電流
        ic_eq = self.af * ieq_f - ieq_r
        ib_eq = (1.0 - self.af) * ieq_f + (1.0 - self.ar) * ieq_r
        ie_eq = -ieq_f + self.ar * ieq_r

        # 依照 PNP / NPN 調整真實電流方向
        ic_eq *= self.bjt_type
        ib_eq *= self.bjt_type
        ie_eq *= self.bjt_type

        # 🚀 6. 蓋上 3x3 完美 Jacobian 矩陣！
        # SPICE 黑魔法：不管 NPN 還是 PNP，小信號電導矩陣 G 是完全一樣的！
        g_cc = g_r
        g_cb = self.af * g_f - g_r
        g_ce = -self.af * g_f

        g_bc = -(1.0 - self.ar) * g_r
        g_bb = (1.0 - self.af) * g_f + (1.0 - self.ar) * g_r
        g_be = -(1.0 - self.af) * g_f

        g_ec = -self.ar * g_r
        g_eb = -g_f + self.ar * g_r
        g_ee = g_f

        nodes = [self.nc, self.nb, self.ne]
        g_matrix = [
            [g_cc, g_cb, g_ce],
            [g_bc, g_bb, g_be],
            [g_ec, g_eb, g_ee]
        ]
        i_vector = [ic_eq, ib_eq, ie_eq]

        for i in range(3):
            if nodes[i] > 0:
                b[nodes[i] - 1] -= i_vector[i]  # 電流源移到 RHS
                for j in range(3):
                    if nodes[j] > 0:
                        A[nodes[i] - 1, nodes[j] - 1] += g_matrix[i][j]

    def stamp(self, A, b, extra_idx=None, ctx=None):
        mode = ctx.get('mode', 'op') if ctx else 'op'
        if mode == 'ac':
            # 🚀 交流分析：直接拿 DC OP 算出來的斜率蓋矩陣
            g_cc = self.gr_ac
            g_cb = self.af * self.gf_ac - self.gr_ac
            g_ce = -self.af * self.gf_ac

            g_bc = -(1.0 - self.ar) * self.gr_ac
            g_bb = (1.0 - self.af) * self.gf_ac + (1.0 - self.ar) * self.gr_ac
            g_be = -(1.0 - self.af) * self.gf_ac

            g_ec = -self.ar * self.gr_ac
            g_eb = -self.gf_ac + self.ar * self.gr_ac
            g_ee = self.gf_ac

            nodes = [self.nc, self.nb, self.ne]
            g_matrix = [
                [g_cc, g_cb, g_ce],
                [g_bc, g_bb, g_be],
                [g_ec, g_eb, g_ee]
            ]

            for i in range(3):
                if nodes[i] > 0:
                    for j in range(3):
                        if nodes[j] > 0:
                            A[nodes[i] - 1, nodes[j] - 1] += complex(g_matrix[i][j], 0.0)