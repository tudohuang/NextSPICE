from . import linalg_core as la
from .model import Resistor, VoltageSource, Diode, Capacitor
import math 

class Circuit:
    def __init__(self):
        self.components = []
        self.node_map = {"GND": 0, "0": 0}
        self.rev_node_map = {0: "0"} # 反向映射，用於更新狀態
        self.next_node_id = 1
        self.v_source_count = 0

    def get_node(self, name):
        name = str(name)
        if name not in self.node_map:
            nid = self.next_node_id
            self.node_map[name] = nid
            self.rev_node_map[nid] = name
            self.next_node_id += 1
        return self.node_map[name]

    def add_component(self, comp):
        # 注入 v_id 給電壓源
        if hasattr(comp, 'v_id'):
            comp.v_id = self.v_source_count
            self.v_source_count += 1
        
        # 關鍵修正：將節點名稱注入元件，讓 Capacitor.update_state 不會 KeyError
        if hasattr(comp, 'n1'):
            comp.n1_name = self.rev_node_map.get(comp.n1, "0")
        if hasattr(comp, 'n2'):
            comp.n2_name = self.rev_node_map.get(comp.n2, "0")
            
        self.components.append(comp)

    def solve_dc(self, max_iter=100, tol=1e-6, dt=None):
        num_node_vars = self.next_node_id - 1
        dim = num_node_vars + self.v_source_count
        v_guess = [0.0] * dim
        
        for i in range(max_iter):
            A = la.create_matrix(dim)
            b = [0.0] * dim

            # 關鍵修正：必須傳遞 dt 參數，電容才能正確蓋章
            for comp in self.components:
                comp.stamp(A, b, dim, num_node_vars, v_guess, dt=dt)

            try:
                v_new = la.gauss_solve(dim, A, b)
            except ValueError:
                raise ValueError("矩陣奇異。請檢查電路是否有懸空節點（例如橋式整流需補 100Meg 地參考）。")

            diff = max(abs(v_new[j] - v_guess[j]) for j in range(dim))
            if diff < tol:
                return {name: (0.0 if idx == 0 else v_new[idx-1]) 
                        for name, idx in self.node_map.items()}
            
            v_guess = v_new
            
        raise ValueError(f"電路在 {max_iter} 次迭代內未收斂。")

    def solve_transient(self, t_stop, dt):
        t = 0.0
        results = []
        t_axis = []
        
        # 初始化電容狀態
        for comp in self.components:
            if hasattr(comp, 'v_prev'): comp.v_prev = 0.0

        while t <= t_stop:
            # 支援時變電源更新
            for comp in self.components:
                if hasattr(comp, 'update_time'):
                    comp.update_time(t)
                # demo.py 內的臨時寫法相容性處理
                elif isinstance(comp, VoltageSource) and not hasattr(comp, 'func'):
                    comp.val = 10.0 * math.sin(2 * math.pi * 60 * t)

            try:
                # 執行包含 dt 的 DC 求解（處理電容 companion model）
                sol = self.solve_dc(dt=dt) 
                
                t_axis.append(t)
                results.append(sol)
                
                # 更新電容的歷史電壓 v_prev
                for comp in self.components:
                    if hasattr(comp, 'update_state'):
                        comp.update_state(sol)
                        
            except Exception as e:
                print(f"Time {t}s: Convergence failed! {e}")
                break
                
            t += dt
            
        return t_axis, results


def parse_unit(val_str):
    val_str = val_str.upper()
    if "MEG" in val_str:
        return float(val_str.replace("MEG", "")) * 1e6
    
    units = {
        'T': 1e12, 'G': 1e9, 'K': 1e3,
        'M': 1e-3, 'U': 1e-6, 'N': 1e-9, 'P': 1e-12, 'F': 1e-15
    }
    
    for unit, factor in units.items():
        if val_str.endswith(unit):
            return float(val_str[:-len(unit)]) * factor
    return float(val_str)


def load_spice_netlist(file_content, ckt_object):
    lines = file_content.split('\n')
    for line in lines:
        line = line.strip()
        if not line or line.startswith('*') or line.startswith('#'):
            continue
        
        tokens = line.split()
        if len(tokens) < 4: continue
        
        element_name = tokens[0].upper()
        n1 = ckt_object.get_node(tokens[1])
        n2 = ckt_object.get_node(tokens[2])
        value = parse_unit(tokens[3])
        
        if element_name.startswith('R'):
            ckt_object.add_component(Resistor(n1, n2, value))
            
        elif element_name.startswith('V'):
            ckt_object.add_component(VoltageSource(n1, n2, value))

        elif element_name.startswith('D'):
            ckt_object.add_component(Diode(n1, n2, Is=1e-12, Vt=0.026)) 


