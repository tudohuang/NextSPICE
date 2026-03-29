# nextspice/engine/utils/nonlinear_helpers.py

import math
from .constants import LOG_FLOOR

def adaptive_junction_clamp(v_new, v_old, vt, v_crit):
    """
    完美的 PN 接面自適應阻尼器 (Newton-Raphson Damping)。
    防止疊代時接面電壓暴衝導致指數溢位，當變動過大時將指數成長壓平為對數成長。
    可用於 Diode, BJT, 以及未來包含 PN 接面的進階 MOSFET 模型。
    """
    delta = v_new - v_old
    two_vt = 2.0 * vt
    
    if v_new > v_crit and abs(delta) > two_vt:
        if v_old > 0:
            scaled = delta / vt
            if scaled > 0:
                v_new = v_old + vt * (2.0 + math.log(max(scaled - 2.0, LOG_FLOOR)))
            else:
                v_new = v_old - vt * (2.0 + math.log(max(2.0 - scaled, LOG_FLOOR)))
        else:
            v_new = vt * math.log(max(v_new / vt, LOG_FLOOR))
    elif v_new < 0:
        floor = (-v_old - 1.0) if v_old > 0 else (2.0 * v_old - 1.0)
        v_new = max(v_new, floor)
        
    return v_new