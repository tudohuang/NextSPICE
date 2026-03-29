import argparse
import os
import sys
import datetime
import numpy as np

# 確保引用路徑正確
from nextspice.core.compiler import SpiceParser
from nextspice.core.circuit import Circuit
from nextspice.engine.solver import Simulator

class ReportGenerator:
    """負責將模擬結果格式化為 Markdown 報告"""
    def __init__(self, filename):
        self.filename = filename
        self.content = [f"# NextSPICE Batch Simulation Report\n", 
                        f"- **Generated At**: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n",
                        f"- **Engine**: NextSPICE v0.3.1 (Industrial Suite)\n",
                        "---\n"]

    def add_section(self, title, text):
        self.content.append(f"## 📄 {title}\n")
        self.content.append(f"{text}\n")
        self.content.append("---\n")

    def save(self):
        with open(self.filename, 'w', encoding='utf-8') as f:
            f.writelines(self.content)
        print(f"[REPORT] Full detailed report saved to: {self.filename}")

def simulate_single_file(file_path):
    """核心模擬邏輯：收集完整的診斷與分析數據"""
    file_results = []
    
    # --- Phase 1: Compiler ---
    parser = SpiceParser(file_path=file_path)
    parsed_data = parser.compile()
    
    # 詳細紀錄 Parser 診斷
    diags = parsed_data.get("diagnostics", [])
    errors = [d for d in diags if d['severity'] == "ERROR"]
    warnings = [d for d in diags if d['severity'] == "WARNING"]
    
    diag_md = []
    if errors or warnings:
        diag_md.append("### 🛠️ Compiler & Builder Diagnostics\n")
        for d in diags:
            icon = "❌" if d['severity'] == "ERROR" else "⚠️"
            diag_md.append(f"- {icon} **[{d['severity']}]** Line {d.get('line', '?')}: {d['message']}")
        
    if errors:
        return "\n".join(diag_md) + "\n\n**Status**: ⛔ Compilation blocked due to syntax errors."

    # --- Phase 2: Circuit Builder ---
    circuit = Circuit(name=os.path.basename(file_path))
    build_res = circuit.build_from_json(parsed_data["circuit"])
    
    if build_res.warnings or build_res.errors:
        if not diag_md: diag_md.append("### 🛠️ Compiler & Builder Diagnostics\n")
        for w in build_res.warnings:
            diag_md.append(f"- ⚠️ **[WARNING]** {w}")
        for e in build_res.errors:
            diag_md.append(f"- ❌ **[ERROR]** {e}")
            
    if not build_res.success:
        return "\n".join(diag_md) + "\n\n**Status**: ⛔ Circuit build failed."

    # 紀錄成功建立的節點資訊
    diag_md.append(f"\n*✓ Circuit successfully mapped to MNA matrix. (Unknown nodes: {circuit.node_mgr.num_unknowns})*\n")
    file_results.extend(diag_md)

    # --- Phase 3: Engine ---
    simulator = Simulator(circuit)
    analyses = parsed_data["circuit"].get("analyses", [])
    
    if not analyses:
        file_results.append("> ℹ️ No analysis directives (.OP, .AC, .TRAN) found in netlist.\n")
        return "\n".join(file_results)

    for analysis in analyses:
        atype = analysis["type"]
        
        # ==== OP 分析 ====
        if atype == "op":
            file_results.append("### ⚡ .OP (Operating Point) Analysis\n")
            res = simulator.solve_op()
            
            if res.status == "SUCCESS":
                file_results.append(f"- **Solve Time**: `{res.solve_time*1000:.3f} ms`")
                file_results.append(f"- **Max Residual**: `{res.residual:.2e}` (Solver Precision)\n")
                
                table = "| Node / Branch | Value | Unit |\n| :--- | :--- | :--- |\n"
                report = simulator.get_full_report(res.x)
                for name, val in report.items():
                    unit = "A" if name.startswith("I(") else "V"
                    table += f"| `{name}` | `{val:.6e}` | {unit} |\n"
                file_results.append(table)
            else:
                file_results.append(f"> ❌ **OP Solve Failed**: {res.status} - {res.error_msg}\n")
                
        # ==== AC 分析 ====
        elif atype == "ac":
            file_results.append("### 📈 .AC (Frequency Sweep) Analysis\n")
            file_results.append(f"- **Sweep Type**: {analysis.get('sweep', 'N/A')}")
            file_results.append(f"- **Range**: {analysis.get('fstart', 'N/A')} Hz to {analysis.get('fstop', 'N/A')} Hz\n")
            
            ac_results = simulator.solve_ac(analysis['fstart'], analysis['fstop'], analysis['points'], analysis['sweep'])
            
            # 尋找輸出探針節點 (優先找 OUT，否則隨便抓一個有效節點)
            out_node = "OUT" if "OUT" in circuit.node_mgr.mapping else None
            if not out_node and circuit.node_mgr.num_unknowns > 0:
                out_node = circuit.node_mgr.get_name(1)
                
            if out_node:
                out_idx = circuit.node_mgr.mapping.get(out_node) - 1
                table = f"| Freq (Hz) | Mag (dB) @ `{out_node}` | Phase (deg) | Status |\n| :--- | :--- | :--- | :--- |\n"
                
                for r in ac_results:
                    if r["status"] == "SUCCESS":
                        v_cplx = r["x"][out_idx]
                        mag_db = 20 * np.log10(np.abs(v_cplx) + 1e-20)
                        phase = np.angle(v_cplx, deg=True)
                        table += f"| {r['freq']:.2e} | `{mag_db:>8.3f}` | `{phase:>8.3f}` | ✓ |\n"
                    else:
                        table += f"| {r['freq']:.2e} | N/A | N/A | ❌ {r['status']} |\n"
                file_results.append(table)
            else:
                file_results.append("> ⚠️ **Warning**: No valid probe node found to generate AC report.\n")
                
        # ==== DC / TRAN 佔位符 ====

        # ==== DC 分析 ====
        elif atype == "dc":
            file_results.append("### 🔋 .DC (DC Sweep) Analysis\n")
            source_name = analysis.get("source", "N/A")
            v_start = analysis.get("start", 0)
            v_stop = analysis.get("stop", 0)
            v_step = analysis.get("step", 0)

            file_results.append(f"- **Sweep Source**: `{source_name}`")
            file_results.append(f"- **Range**: `{v_start} V` to `{v_stop} V` (Step: `{v_step} V`)\n")

            # 呼叫 Solver 執行掃描
            dc_results = simulator.solve_dc_sweep(source_name, v_start, v_stop, v_step)

            # 錯誤處理：找不到指定的電源
            if not dc_results or ("status" in dc_results[0] and dc_results[0]["status"] == "ERROR"):
                err_msg = dc_results[0].get("msg", "Unknown error") if dc_results else "No data generated."
                file_results.append(f"> ❌ **DC Sweep Failed**: {err_msg}\n")
                continue

            # 抓取第一個成功收斂的點，用來動態建立表格的標題列 (Headers)
            first_success = next((r for r in dc_results if r["result"].status == "SUCCESS"), None)
            
            if first_success:
                report_keys = list(simulator.get_full_report(first_success["result"].x).keys())
                
                # 建立 Markdown 表格標題
                header = f"| Sweep `{source_name}` (V) | " + " | ".join([f"`{k}`" for k in report_keys]) + " | Status |\n"
                separator = "| :--- | " + " | ".join(["---:" for _ in report_keys]) + " | :--- |\n"
                table = header + separator

                # 填入每一個掃描點的數據
                for r in dc_results:
                    v_in = r["v_in"]
                    solve_res = r["result"]
                    
                    if solve_res.status == "SUCCESS":
                        row_report = simulator.get_full_report(solve_res.x)
                        row_str = f"| **{v_in:.3f}** | "
                        row_str += " | ".join([f"{row_report.get(k, 0):.5e}" for k in report_keys])
                        row_str += " | ✓ |\n"
                        table += row_str
                    else:
                        table += f"| **{v_in:.3f}** | " + " | ".join(["N/A" for _ in report_keys]) + f" | ❌ {solve_res.status} |\n"
                
                file_results.append(table)
            else:
                file_results.append("> ❌ **DC Sweep Failed**: All sweep points failed to converge.\n")
        elif atype == "tran":
             file_results.append("### ⏱️ .TRAN (Transient) Analysis\n*(Transient data processing pending implementation)*\n")

    return "\n".join(file_results)

def main():
    cli_parser = argparse.ArgumentParser(description="NextSPICE Batch Simulator")
    group = cli_parser.add_mutually_exclusive_group(required=True)
    group.add_argument('-f', '--file', type=str, help="Single netlist file")
    group.add_argument('-d', '--dir', type=str, help="Directory containing .cir files")
    
    cli_parser.add_argument('-o', '--output', type=str, default="sim_report.md", help="Output Markdown report filename")
    
    args = cli_parser.parse_args()
    report_gen = ReportGenerator(args.output)

    # 決定處理路徑
    target_files = []
    if args.file:
        target_files.append(args.file)
    else:
        if os.path.exists(args.dir):
            target_files = [os.path.join(args.dir, f) for f in os.listdir(args.dir) if f.endswith(('.cir', '.sp'))]
        
    if not target_files:
        print("❌ No valid netlist files found.")
        return

    print(f"[BATCH] Starting simulation for {len(target_files)} files...")

    for f_path in target_files:
        f_name = os.path.basename(f_path)
        print(f"Processing: {f_name}")
        
        result_md = simulate_single_file(f_path)
        report_gen.add_section(f_name, result_md)

    report_gen.save()

if __name__ == "__main__":
    main()