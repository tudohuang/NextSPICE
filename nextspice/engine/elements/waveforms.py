import re
import math
from nextspice.utils.unit_conv import UnitConverter as unit_conv

def _ensure_numeric(raw_args, wtype):
    """
    確保所有解析出來的參數都是合法的數值 (float / int)。
    防止未展開的變數 (如 {VAR}) 進入數學運算導致靜默錯誤或崩潰。
    """
    numeric_args = []
    for x in raw_args:
        val = unit_conv.parse(x)
        if not isinstance(val, (int, float)):
            raise ValueError(f"[{wtype}] 遇到無法解析的非數值參數: '{x}'。請確認變數是否已在 Parser 階段完全展開。")
        numeric_args.append(float(val))
    return numeric_args

def eval_source_waveform(tran_str, dc_value, t):
    """
    根據當下時間 t，計算時域波形的瞬間數值 (電壓或電流共用)。
    作為波形分發器 (Router)，負責解析字串並呼叫對應的純數學計算函數。
    """
    if not tran_str:
        return float(dc_value)

    tran_upper = tran_str.upper()
    
    match = re.search(r'\((.*?)\)', tran_upper)
    if not match:
        return float(dc_value)
        
    raw_args = match.group(1).replace(',', ' ').split()
    if not raw_args:
        return float(dc_value)

    # === 根據波形前綴進行路由與嚴格檢查 ===
    if tran_upper.startswith("SIN"):
        args = _ensure_numeric(raw_args, "SIN")
        return _eval_sin(args, t)
        
    elif tran_upper.startswith("PULSE"):
        args = _ensure_numeric(raw_args, "PULSE")
        return _eval_pulse(args, t)
        
    elif tran_upper.startswith("PWL"):
        args = _ensure_numeric(raw_args, "PWL")
        
        # 🚀 致命防呆：PWL 必須是 (時間, 電壓) 座標對
        if len(args) % 2 != 0:
            raise ValueError(f"[PWL] 參數必須是成對的 (時間, 數值)，但目前解析出 {len(args)} 個參數: {raw_args}")
        if len(args) < 2:
            return float(dc_value)
            
        return _eval_pwl(args, t)

    return float(dc_value)


# =====================================================================
# 🧮 以下為各波形的純數學計算邏輯 (Pure Functions)
# =====================================================================

def _eval_sin(args, t):
    """計算正弦波 SIN(VO VA FREQ TD THETA)"""
    vo = args[0] if len(args) > 0 else 0.0      # DC 偏移量
    va = args[1] if len(args) > 1 else 0.0      # 振幅
    freq = args[2] if len(args) > 2 else 0.0    # 頻率
    td = args[3] if len(args) > 3 else 0.0      # 延遲時間
    theta = args[4] if len(args) > 4 else 0.0   # 阻尼系數
    
    if t < td:
        return vo
    return vo + va * math.exp(-theta * (t - td)) * math.sin(2 * math.pi * freq * (t - td))


def _eval_pulse(args, t):
    """計算脈衝方波 PULSE(V1 V2 TD TR TF PW PER)"""
    v1 = args[0] if len(args) > 0 else 0.0      # 初始值
    v2 = args[1] if len(args) > 1 else 0.0      # 脈衝值
    td = args[2] if len(args) > 2 else 0.0      # 延遲時間
    tr = args[3] if len(args) > 3 else 0.0      # 上升時間
    tf = args[4] if len(args) > 4 else 0.0      # 下降時間
    pw = args[5] if len(args) > 5 else 1.0      # 脈衝寬度
    per = args[6] if len(args) > 6 else 1.0     # 週期

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


def _eval_pwl(args, t):
    """計算分段線性波形 PWL(T1 V1 T2 V2 ...)"""
    # 轉換為 (時間, 數值) 座標對陣列
    pts = [(args[i], args[i+1]) for i in range(0, len(args)-1, 2)]
    
    # 狀態 1：時間還沒到第一個點
    if t <= pts[0][0]:
        return pts[0][1]
        
    # 狀態 2：時間已經超過最後一個點
    if t >= pts[-1][0]:
        return pts[-1][1]
        
    # 狀態 3：尋找對應的區間進行「線性內插」
    for i in range(len(pts) - 1):
        t1, v1 = pts[i]
        t2, v2 = pts[i+1]
        
        if t1 <= t <= t2:
            # 防呆：如果兩個點時間一樣 (垂直線)，直接回傳後面的值避免除以零
            if t2 == t1:
                return v2
            # 線性內插公式：V(t) = V1 + (V2 - V1) * (t - t1) / (t2 - t1)
            return v1 + (v2 - v1) * (t - t1) / (t2 - t1)
            
    return pts[-1][1] # Fallback 防呆