from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.responses import HTMLResponse
import uvicorn
import numpy as np
import traceback

# 🚀 召喚你的 NextSPICE 核心引擎！
from nextspice.core.compiler import SpiceParser
from nextspice.core.circuit import Circuit
from nextspice.engine.solver import Simulator

app = FastAPI()

class NetlistRequest(BaseModel):
    netlist: str

@app.get("/", response_class=HTMLResponse)
async def get_index():
    with open("index.html", "r", encoding="utf-8") as f:
        return f.read()

@app.post("/api/simulate")
async def run_simulation(request: NetlistRequest):
    raw_netlist = request.netlist.strip()
    response_data = {"status": "success", "logs": [], "plots": [], "layout": {}, "op_results": {}}
    
    def log(msg):
        response_data["logs"].append(msg)

    try:
        # --- Phase 1: Compile ---
        parser = SpiceParser(content=raw_netlist)
        parsed_data = parser.compile()
        
        has_error = False
        for d in parsed_data.get("diagnostics", []):
            log(f"[{d['severity']}] Line {d.get('line', '?')}: {d['message']}")
            if d['severity'] == "ERROR": has_error = True
        if has_error:
            return {"status": "error", "logs": response_data["logs"], "plots": [], "layout": {}}

        # --- Phase 2: Build ---
        circuit = Circuit(name="Web_Sim")
        build_res = circuit.build_from_json(parsed_data["circuit"])
        if not build_res.success:
            for err in build_res.errors: log(f"[BUILD ERROR] {err}")
            return {"status": "error", "logs": response_data["logs"], "plots": [], "layout": {}}

        # --- Phase 3: Solve ---
        simulator = Simulator(circuit)
        analyses = parsed_data["circuit"].get("analyses", [])
        if not analyses:
            log("⚠️ 找不到任何分析指令 (.OP, .TRAN, .AC, .DC)")
            return response_data

        nodes_to_plot = [name for name in circuit.node_mgr.mapping.keys() if name != "0"]

        for analysis in analyses:
            atype = analysis["type"]
            
            if atype == "op":
                log("--- .OP Analysis ---")
                res = simulator.solve_op()
                if res.status == "SUCCESS":
                    report = simulator.get_full_report(res.x)
                    response_data["op_results"] = report  # 🚀 關鍵新增：把字典直接塞給前端！
                    for name, val in report.items():
                        unit = "A" if name.startswith("I(") else "V"
                        log(f"{name:<10} | {val:>12.5e} {unit}")

            elif atype == "tran":
                log(f"--- .TRAN Analysis (0 to {analysis['tstop']*1000} ms) ---")
                tran_results = simulator.solve_tran(analysis['tstep'], analysis['tstop'])
                times = [r["time"] for r in tran_results if r["status"] == "SUCCESS"]
                
                response_data["layout"] = {"title": "Transient Response", "xaxis": "Time (s)", "yaxis": "Voltage (V)"}
                
                for node_name in nodes_to_plot:
                    idx = circuit.node_mgr.mapping[node_name] - 1
                    v_data = [r["x"][idx] for r in tran_results if r["status"] == "SUCCESS"]
                    ls = "dash" if "IN" in node_name.upper() else "solid"
                    response_data["plots"].append({"name": f"V({node_name})", "x": times, "y": v_data, "type": ls})
                log(f"✓ 完成 {len(times)} 個時間步長。")

            elif atype == "ac":
                log(f"--- .AC Analysis ({analysis['fstart']}Hz to {analysis['fstop']}Hz) ---")
                ac_results = simulator.solve_ac(analysis['fstart'], analysis['fstop'], analysis['points'], analysis['sweep'])
                freqs = [r["freq"] for r in ac_results if r["status"] == "SUCCESS"]
                
                response_data["layout"] = {"title": "AC Frequency Response", "xaxis": "Frequency (Hz)", "yaxis": "Magnitude (dB)", "is_ac": True}
                
                for node_name in nodes_to_plot:
                    if 'IN' in node_name.upper(): continue
                    idx = circuit.node_mgr.mapping[node_name] - 1
                    v_cplx = [r["x"][idx] for r in ac_results if r["status"] == "SUCCESS"]
                    mags = [20 * np.log10(np.abs(v) + 1e-20) for v in v_cplx]
                    # 傳送 Mag 給前端畫圖
                    response_data["plots"].append({"name": f"Mag V({node_name})", "x": freqs, "y": mags, "type": "solid"})
                log(f"✓ 完成 {len(freqs)} 個頻率點。")
                
    except Exception as e:
        log(f"❌ 核心引擎崩潰: {str(e)}")
        traceback.print_exc()

    return response_data

