from .base import BaseElement
from .waveforms import eval_source_waveform
import math
import cmath

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

