import math
from . import linalg_core as la

class Resistor:
    def __init__(self, n1, n2, val):
        self.n1 = n1
        self.n2 = n2
        self.val = float(val)

    def stamp(self, A, b, dim, num_node_vars, v_guess=None, dt=None):
        g = 1.0 / self.val
        if self.n1 > 0: la.stamping(A, self.n1-1, self.n1-1, dim, g)
        if self.n2 > 0: la.stamping(A, self.n2-1, self.n2-1, dim, g)
        if self.n1 > 0 and self.n2 > 0:
            la.stamping(A, self.n1-1, self.n2-1, dim, -g)
            la.stamping(A, self.n2-1, self.n1-1, dim, -g)

class VoltageSource:
    def __init__(self, n1, n2, val=0.0, func=None):
        self.n1 = n1
        self.n2 = n2
        self.val = float(val)
        self.func = func # 支援 lambda t: ...
        self.v_id = None 

    def update_time(self, t):
        """根據目前時間更新電壓值"""
        if self.func:
            self.val = float(self.func(t))

    def stamp(self, A, b, dim, num_node_vars, v_guess=None, dt=None):
        v_row = num_node_vars + self.v_id
        if self.n1 > 0:
            la.stamping(A, self.n1-1, v_row, dim, 1.0)
            la.stamping(A, v_row, self.n1-1, dim, 1.0)
        if self.n2 > 0:
            la.stamping(A, self.n2-1, v_row, dim, -1.0)
            la.stamping(A, v_row, self.n2-1, dim, -1.0)
        b[v_row] = self.val

class CurrentSource:
    def __init__(self, n1, n2, val):
        self.n1 = n1  
        self.n2 = n2  
        self.val = float(val)

    def stamp(self, A, b, dim, num_node_vars, v_guess=None, dt=None):
        if self.n1 > 0:
            b[self.n1-1] -= self.val
        if self.n2 > 0:
            b[self.n2-1] += self.val

class Diode:
    def __init__(self, n1, n2, Is=1e-12, Vt=0.026):
        self.n1 = n1
        self.n2 = n2
        self.Is = Is
        self.Vt = Vt
    
    def stamp(self, A, b, dim, num_node_vars, v_guess, dt=None):
        v1 = 0 if self.n1 == 0 else v_guess[self.n1-1]
        v2 = 0 if self.n2 == 0 else v_guess[self.n2-1]
        vd = v1 - v2
        
        # 限制電壓防止指數爆炸，增加收斂穩定性
        vd_clamped = min(vd, 0.8) 
        
        exp_val = math.exp(vd_clamped / self.Vt)
        curr = self.Is * (exp_val - 1)
        geq = (self.Is / self.Vt) * exp_val 
        ieq = curr - geq * vd_clamped 

        if self.n1 > 0:
            la.stamping(A, self.n1-1, self.n1-1, dim, geq)
            b[self.n1-1] -= ieq
        if self.n2 > 0:
            la.stamping(A, self.n2-1, self.n2-1, dim, geq)
            b[self.n2-1] += ieq
        if self.n1 > 0 and self.n2 > 0:
            la.stamping(A, self.n1-1, self.n2-1, dim, -geq)
            la.stamping(A, self.n2-1, self.n1-1, dim, -geq)

class Capacitor:
    def __init__(self, n1, n2, value):
        self.n1 = n1
        self.n2 = n2
        self.value = float(value)
        self.v_prev = 0.0  # 儲存歷史電壓狀態
        # 在 Circuit.get_node 之後，這兩個名稱需要被 Circuit 注入
        self.n1_name = None 
        self.n2_name = None

    def stamp(self, A, b, dim, num_node_vars, v_guess=None, dt=None):
        """實作 Backward Euler 伴隨模型"""
        if dt is None: return # DC 分析時電容視為斷路
        
        geq = self.value / dt
        ihist = geq * self.v_prev # 歷史電流源

        if self.n1 > 0:
            la.stamping(A, self.n1-1, self.n1-1, dim, geq)
            b[self.n1-1] += ihist 
        if self.n2 > 0:
            la.stamping(A, self.n2-1, self.n2-1, dim, geq)
            b[self.n2-1] -= ihist
        if self.n1 > 0 and self.n2 > 0:
            la.stamping(A, self.n1-1, self.n2-1, dim, -geq)
            la.stamping(A, self.n2-1, self.n1-1, dim, -geq)

    def update_state(self, sol):
        """更新電容跨壓供下一步使用"""
        v1 = sol[self.n1_name] if self.n1 > 0 else 0
        v2 = sol[self.n2_name] if self.n2 > 0 else 0
        self.v_prev = v1 - v2