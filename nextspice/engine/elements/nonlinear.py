import math
import cmath
from .base import BaseElement
# 🚀 補齊所有需要的常數
from nextspice.utils.constants import GMIN_NONLINEAR, EXP_LIMIT, BOLTZMANN_K, CHARGE_Q
from nextspice.utils.nonlinear_helpers import adaptive_junction_clamp

class Diode(BaseElement):
    def __init__(self, name, n1, n2, is_sat=1e-14, n=1.0, temp=300.15):
        super().__init__(name)
        self.n1 = n1
        self.n2 = n2
        self.is_nonlinear = True  
        
        self.is_sat = float(is_sat)
        self.n = float(n)
        self.temp = float(temp)
        
        self.vt = (BOLTZMANN_K * self.temp) / CHARGE_Q
        self.v_prev = 0.0

    @property
    def vcrit(self):
        nVt = self.n * self.vt
        return nVt * math.log(nVt / (math.sqrt(2) * self.is_sat))

    def stamp_nonlinear(self, A, b, x_old, extra_idx=None, ctx=None):
        v_p = x_old[self.n1 - 1] if self.n1 > 0 else 0.0
        v_n = x_old[self.n2 - 1] if self.n2 > 0 else 0.0
        vd_raw = v_p - v_n
        
        # 🚀 移除 self. 前綴，直接使用共用 helper
        vd_safe = adaptive_junction_clamp(vd_raw, self.v_prev, self.vt * self.n, self.vcrit)
        self.v_prev = vd_safe 
        
        nVt = self.n * self.vt
        # 🚀 換成 EXP_LIMIT
        exp_term = math.exp(min(vd_safe / nVt, EXP_LIMIT))
        
        id_val = self.is_sat * (exp_term - 1.0)
        gd_val = (self.is_sat / nVt) * exp_term
        
        # 🚀 換成 GMIN_NONLINEAR
        gd_val += GMIN_NONLINEAR
        i_eq = id_val - gd_val * vd_safe + (GMIN_NONLINEAR * vd_safe)
        
        if self.n1 > 0:
            A[self.n1 - 1, self.n1 - 1] += gd_val
            b[self.n1 - 1] -= i_eq
        if self.n2 > 0:
            A[self.n2 - 1, self.n2 - 1] += gd_val
            b[self.n2 - 1] += i_eq
        if self.n1 > 0 and self.n2 > 0:
            A[self.n1 - 1, self.n2 - 1] -= gd_val
            A[self.n2 - 1, self.n1 - 1] -= gd_val


class BJT(BaseElement):
    def __init__(self, name, nc, nb, ne, bjt_type='NPN', is_sat=1e-14, bf=100.0, br=1.0, temp=300.15):
        super().__init__(name)
        self.nc = nc  # Collector
        self.nb = nb  # Base
        self.ne = ne  # Emitter
        self.is_nonlinear = True
        
        self.bjt_type = 1.0 if bjt_type.upper() == 'NPN' else -1.0

        self.is_sat = float(is_sat)
        self.bf = float(bf)  
        self.br = float(br)  
        self.temp = float(temp)

        self.af = self.bf / (self.bf + 1.0)
        self.ar = self.br / (self.br + 1.0)

        self.vt = (BOLTZMANN_K * self.temp) / CHARGE_Q

        self.vbe_prev = 0.0
        self.vbc_prev = 0.0

        self.gf_ac = 0.0
        self.gr_ac = 0.0

    @property
    def vcrit_f(self):
        return self.vt * math.log(self.vt / (math.sqrt(2) * (self.is_sat / self.af)))

    @property
    def vcrit_r(self):
        return self.vt * math.log(self.vt / (math.sqrt(2) * (self.is_sat / self.ar)))

    def stamp_nonlinear(self, A, b, x_old, extra_idx=None, ctx=None):
        vc = x_old[self.nc - 1] if self.nc > 0 else 0.0
        vb = x_old[self.nb - 1] if self.nb > 0 else 0.0
        ve = x_old[self.ne - 1] if self.ne > 0 else 0.0

        vbe_raw = self.bjt_type * (vb - ve)
        vbc_raw = self.bjt_type * (vb - vc)

        # 🚀 移除 self. 前綴
        vbe_safe = adaptive_junction_clamp(vbe_raw, self.vbe_prev, self.vt, self.vcrit_f)
        vbc_safe = adaptive_junction_clamp(vbc_raw, self.vbc_prev, self.vt, self.vcrit_r)

        self.vbe_prev = vbe_safe
        self.vbc_prev = vbc_safe

        # 🚀 換成 EXP_LIMIT
        exp_f = math.exp(min(vbe_safe / self.vt, EXP_LIMIT))
        exp_r = math.exp(min(vbc_safe / self.vt, EXP_LIMIT))

        i_f = (self.is_sat / self.af) * (exp_f - 1.0)
        g_f = (self.is_sat / (self.af * self.vt)) * exp_f

        i_r = (self.is_sat / self.ar) * (exp_r - 1.0)
        g_r = (self.is_sat / (self.ar * self.vt)) * exp_r

        # 🚀 換成 GMIN_NONLINEAR
        g_f += GMIN_NONLINEAR
        g_r += GMIN_NONLINEAR

        self.gf_ac = g_f
        self.gr_ac = g_r

        ieq_f = i_f - g_f * vbe_safe
        ieq_r = i_r - g_r * vbc_safe

        ic_eq = self.af * ieq_f - ieq_r
        ib_eq = (1.0 - self.af) * ieq_f + (1.0 - self.ar) * ieq_r
        ie_eq = -ieq_f + self.ar * ieq_r

        ic_eq *= self.bjt_type
        ib_eq *= self.bjt_type
        ie_eq *= self.bjt_type

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
                b[nodes[i] - 1] -= i_vector[i] 
                for j in range(3):
                    if nodes[j] > 0:
                        A[nodes[i] - 1, nodes[j] - 1] += g_matrix[i][j]

    def stamp(self, A, b, extra_idx=None, ctx=None):
        mode = ctx.get('mode', 'op') if ctx else 'op'
        if mode == 'ac':
            # 🚀 加入 Fail-Fast 防護網
            if self.gf_ac == 0.0 and self.gr_ac == 0.0:
                raise RuntimeError(f"[BJT] {self.name} AC 分析前未建立 DC 工作點！請確保已先執行 OP 分析。")
                
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