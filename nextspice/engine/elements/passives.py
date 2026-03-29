import math
from .base import BaseElement
# 🚀 使用精準的分類常數與絕對路徑
from nextspice.utils.constants import GMIN_DC_PULLDOWN, GMIN_BRANCH_PATCH, DEFAULT_DT

class Resistor(BaseElement):
    """
    理想電阻器 (R)
    方程式: I = V / R (蓋入節點導納矩陣)
    """
    def __init__(self, name, n1, n2, value):
        super().__init__(name)
        self.n1, self.n2 = n1, n2
        self.value = float(value)
        
        if self.value <= 0:
            raise ValueError(f"[Resistor] {self.name} 的阻值必須大於 0，目前為 {self.value}")

    def stamp(self, A, b, extra_idx=None, ctx=None):
        g = 1.0 / self.value 
        if self.n1 > 0: A[self.n1 - 1, self.n1 - 1] += g
        if self.n2 > 0: A[self.n2 - 1, self.n2 - 1] += g
        if self.n1 > 0 and self.n2 > 0:
            A[self.n1 - 1, self.n2 - 1] -= g
            A[self.n2 - 1, self.n1 - 1] -= g


class Capacitor(BaseElement):
    """
    理想電容器 (C)
    DC/OP: 視為開路 (加上 GMIN_DC_PULLDOWN 避免節點浮接)
    AC: 複數導納 Y = jωC
    TRAN: Companion Model (Norton 等效)
    """
    def __init__(self, name, n1, n2, value):
        super().__init__(name)
        self.n1, self.n2 = n1, n2
        self.value = float(value)
        self.v_prev = 0.0
        self.i_prev = 0.0
        
        if self.value <= 0:
            raise ValueError(f"[Capacitor] {self.name} 的電容值必須大於 0，目前為 {self.value}")

    def stamp(self, A, b, extra_idx=None, ctx=None):
        ctx = ctx or {}
        mode = ctx.get('mode', 'op')
        
        if mode in ('dc', 'op'):
            # DC OP 視為開路，補上極小電導防止浮接節點導致矩陣無法求解
            if self.n1 > 0: A[self.n1 - 1, self.n1 - 1] += GMIN_DC_PULLDOWN
            if self.n2 > 0: A[self.n2 - 1, self.n2 - 1] += GMIN_DC_PULLDOWN
            if self.n1 > 0 and self.n2 > 0:
                A[self.n1 - 1, self.n2 - 1] -= GMIN_DC_PULLDOWN
                A[self.n2 - 1, self.n1 - 1] -= GMIN_DC_PULLDOWN
                
        elif mode == 'ac':
            freq = ctx.get('freq', 1.0)
            omega = 2.0 * math.pi * freq
            y_c = complex(0, omega * self.value)
            if self.n1 > 0: A[self.n1 - 1, self.n1 - 1] += y_c
            if self.n2 > 0: A[self.n2 - 1, self.n2 - 1] += y_c
            if self.n1 > 0 and self.n2 > 0:
                A[self.n1 - 1, self.n2 - 1] -= y_c
                A[self.n2 - 1, self.n1 - 1] -= y_c
                
        elif mode == 'tran':
            dt = ctx.get('dt', DEFAULT_DT)
            method = ctx.get('integration', 'trapezoidal')
            if method == 'gear2':
                g_eq = 1.5 * self.value / dt
                i_hist = self.value / dt * (2.0 * self.v_prev - 0.5 * getattr(self, 'v_prev2', self.v_prev))
            elif method == 'trapezoidal':
                g_eq = 2.0 * self.value / dt
                i_hist = g_eq * self.v_prev + self.i_prev
            else:
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

    def update_history(self, x, extra_idx=None, ctx=None, **kwargs):
        ctx = ctx or kwargs  
        v_p = x[self.n1 - 1] if self.n1 > 0 else 0.0
        v_n = x[self.n2 - 1] if self.n2 > 0 else 0.0
        v_now = v_p - v_n
        dt = ctx.get('dt')
        method = ctx.get('integration', 'trapezoidal')
        self.v_prev2 = self.v_prev  
        if method == 'trapezoidal' and dt:
            g_eq = 2.0 * self.value / dt
            self.i_prev = g_eq * (v_now - self.v_prev) - self.i_prev
        self.v_prev = v_now


class Inductor(BaseElement):
    """
    理想電感器 (L)
    引入 1 個額外變數 (支路電流 I_L)
    DC/OP: 視為短路
    TRAN: Companion Model (Thevenin 等效)
    """
    def __init__(self, name, n1, n2, value):
        super().__init__(name)
        self.n1, self.n2 = n1, n2
        self.value = float(value)
        self.i_prev, self.v_prev = 0.0, 0.0
        self.extra_vars = 1
        
        if self.value <= 0:
            raise ValueError(f"[Inductor] {self.name} 的電感值必須大於 0")

    def stamp(self, A, b, extra_idx=None, ctx=None):
        if extra_idx is None:
            raise ValueError(f"[{self.name}] 致命錯誤：未分配到 extra_idx")
            
        ctx = ctx or {}
        mode = ctx.get('mode', 'op')
        idx = extra_idx
        
        if mode in ('dc', 'op'):
            if self.n1 > 0:
                A[self.n1 - 1, idx] += 1.0
                A[idx, self.n1 - 1] += 1.0
            if self.n2 > 0:
                A[self.n2 - 1, idx] -= 1.0
                A[idx, self.n2 - 1] -= 1.0
            # 🚀 修正：明確補上 RHS 為 0，並使用支路專用補丁
            b[idx] = 0.0
            A[idx, idx] -= GMIN_BRANCH_PATCH
            
        elif mode == 'ac':
            freq = ctx.get('freq', 1.0)
            omega = 2.0 * math.pi * freq
            z_l = complex(0, omega * self.value)
            if self.n1 > 0:
                A[self.n1 - 1, idx] += 1.0
                A[idx, self.n1 - 1] += 1.0
            if self.n2 > 0:
                A[self.n2 - 1, idx] -= 1.0
                A[idx, self.n2 - 1] -= 1.0
            A[idx, idx] -= z_l
            
        elif mode == 'tran':
            dt = ctx.get('dt', DEFAULT_DT)
            method = ctx.get('integration', 'trapezoidal')
            if method == 'gear2':
                r_eq = 1.5 * self.value / dt
                v_hist = self.value / dt * (2.0 * self.i_prev - 0.5 * getattr(self, 'i_prev2', self.i_prev))
            elif method == 'trapezoidal':
                r_eq = 2.0 * self.value / dt
                v_hist = r_eq * self.i_prev + self.v_prev
            else:
                r_eq = self.value / dt
                v_hist = r_eq * self.i_prev

            if self.n1 > 0:
                A[self.n1 - 1, idx] += 1.0
                A[idx, self.n1 - 1] += 1.0
            if self.n2 > 0:
                A[self.n2 - 1, idx] -= 1.0
                A[idx, self.n2 - 1] -= 1.0
            A[idx, idx] -= r_eq
            b[idx] -= v_hist

    def update_history(self, x, extra_idx=None, ctx=None, **kwargs):
        ctx = ctx or kwargs  
        i_now = x[extra_idx] if extra_idx is not None else 0.0
        v_p = x[self.n1 - 1] if self.n1 > 0 else 0.0
        v_n = x[self.n2 - 1] if self.n2 > 0 else 0.0
        v_now = v_p - v_n
        dt = ctx.get('dt')
        method = ctx.get('integration', 'trapezoidal')
        self.i_prev2 = self.i_prev  
        if method == 'trapezoidal' and dt:
            self.v_prev = v_now
        self.i_prev = i_now


class MutualInductance(BaseElement):
    """
    互感器 (K)
    透過修改所屬兩個電感的轉移阻抗達成耦合
    """
    def __init__(self, name, l1_obj, l2_obj, k_value):
        super().__init__(name)
        self.l1_obj, self.l2_obj = l1_obj, l2_obj
        self.k = float(k_value)
        if not (-1.0 <= self.k <= 1.0):
            raise ValueError(f"[MutualInductance] {self.name} 的 k 必須介於 -1 到 1")
        self.M = self.k * math.sqrt(self.l1_obj.value * self.l2_obj.value)

    def stamp(self, A, b, extra_idx=None, ctx=None):
        ctx = ctx or {}
        extra_map = ctx.get('extra_map', {})
        idx1 = extra_map.get(self.l1_obj)
        idx2 = extra_map.get(self.l2_obj)
        if idx1 is None or idx2 is None: return

        mode = ctx.get('mode', 'op')
        if mode == 'ac':
            freq = ctx.get('freq', 1.0)
            omega = 2.0 * math.pi * freq
            zm = complex(0, omega * self.M)
            A[idx1, idx2] -= zm
            A[idx2, idx1] -= zm
        elif mode == 'tran':
            dt = ctx.get('dt', DEFAULT_DT)
            rm = self.M / dt
            A[idx1, idx2] -= rm
            A[idx2, idx1] -= rm
            b[idx1] -= rm * self.l2_obj.i_prev
            b[idx2] -= rm * self.l1_obj.i_prev