class BaseElement:
    """
    NextSPICE 元件的抽象基底類別 (Interface Contract)
    所有的被動、受控、非線性元件都必須遵守此處定義的 API 介面。
    """
    def __init__(self, name):
        self.name = name
        self.extra_vars = 0
        self.is_nonlinear = False  # 預設為線性元件

    def stamp(self, A, b, extra_idx=None, ctx=None):
        """線性與動態元件的蓋章邏輯 (DC/AC/TRAN)"""
        raise NotImplementedError(f"元件 {self.name} 尚未實作 stamp() 方法")

    def stamp_nonlinear(self, A, b, x_old, extra_idx=None, ctx=None):
        """
        非線性元件的 Newton-Raphson 蓋章邏輯
        必須使用當前疊代電壓 x_old 計算 Jacobian 斜率與等效電流源。
        """
        if self.is_nonlinear:
            raise NotImplementedError(f"非線性元件 {self.name} 必須實作 stamp_nonlinear() 方法")

    def update_history(self, x, extra_idx=None, ctx=None, **kwargs):
        """
        更新動態元件的歷史狀態 (供 TRAN 數值積分使用)。
        注意：未來的重構將會消滅 kwargs，全面改用強型別的 AnalysisContext。
        """
        pass