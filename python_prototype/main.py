from engine.mna import Circuit, load_spice_netlist

netlist_content = """
V1 In GND 12
V2 In GND 10
R1 In Out 2k
R2 Out GND 4k
"""

ckt = Circuit()
load_spice_netlist(netlist_content, ckt)
results = ckt.solve()

for node, voltage in results.items():
    print(f"{node}: {voltage:.4f} V")   