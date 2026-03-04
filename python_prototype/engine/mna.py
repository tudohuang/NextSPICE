from . import linalg_core as la
from .model import Resistor, VoltageSource

class Circuit:
    def __init__(self):
        self.components = []
        self.node_map = {"GND": 0, "0": 0}
        self.next_node_id = 1
        self.v_source_count = 0

    def get_node(self, name):
        name = str(name)
        if name not in self.node_map:
            self.node_map[name] = self.next_node_id
            self.next_node_id += 1
        return self.node_map[name]

    def add_component(self, comp):
            # 檢查元件是否有 v_id 這個屬性 (不管是 None 還是數字)
            if hasattr(comp, 'v_id'):
                comp.v_id = self.v_source_count
                self.v_source_count += 1
            
            self.components.append(comp)
        
    def solve(self):
        num_node_vars = self.next_node_id - 1
        dim = num_node_vars + self.v_source_count
        A = la.create_matrix(dim)
        b = [0.0] * dim

        for comp in self.components:
            comp.stamp(A, b, dim, num_node_vars)

        raw_solution = la.gauss_solve(dim, A, b)
        
        results = {name: (0.0 if idx == 0 else raw_solution[idx-1]) 
                   for name, idx in self.node_map.items()}
        return results

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