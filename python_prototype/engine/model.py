from . import linalg_core as la
class Resistor:
    def __init__(self, n1, n2, val):
        self.n1 = n1
        self.n2 = n2
        self.val = float(val)

    # 必須增加第四個參數，即使沒用到 (可以用 _ 代表忽略)
    def stamp(self, A, b, dim, num_node_vars, v_guess=None):
        g = 1.0 / self.val
        # 這裡的邏輯不變
        if self.n1 > 0: la.stamping(A, self.n1-1, self.n1-1, dim, g)
        if self.n2 > 0: la.stamping(A, self.n2-1, self.n2-1, dim, g)
        if self.n1 > 0 and self.n2 > 0:
            la.stamping(A, self.n1-1, self.n2-1, dim, -g)
            la.stamping(A, self.n2-1, self.n1-1, dim, -g)

class VoltageSource:
    def __init__(self, n1, n2, val):
        self.n1 = n1
        self.n2 = n2
        self.val = float(val)
        self.v_id = None # 由 Circuit 分配

    def stamp(self, A, b, dim, num_node_vars, v_guess=None):
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
        self.n1 = n1  # 流出
        self.n2 = n2  # 流入
        self.val = float(val)

    def stamp(self, A, b, dim, num_node_vars, v_guess=None):
        if self.n1 > 0:
            b[self.n1-1] -= self.val
        if self.n2 > 0:
            b[self.n2-1] += self.val