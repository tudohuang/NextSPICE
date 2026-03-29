import numpy as np
import scipy.sparse
import scipy.sparse.linalg
import time
import math

class SolverResult:
    def __init__(self, x=None, status="SUCCESS", error_msg="",
                 residual=0.0, solve_time=0.0, method_used=""):
        self.x = x
        self.status = status
        self.error_msg = error_msg
        self.residual = residual
        self.solve_time = solve_time
        self.method_used = method_used

    def __repr__(self):
        res_str = f"{self.residual:.2e}" if self.residual is not None else "N/A"
        m = f", method={self.method_used}" if self.method_used else ""
        return (f"SolverResult(status={self.status}, res={res_str}, "
                f"time={self.solve_time*1000:.2f}ms{m})")

# ── 線性求解器工廠 ──
# 支援: spsolve (直接 LU), gmres, bicgstab, cgs, lgmres
ITERATIVE_SOLVERS = {
    'gmres': scipy.sparse.linalg.gmres,
    'bicgstab': scipy.sparse.linalg.bicgstab,
    'cgs': scipy.sparse.linalg.cgs,
    'lgmres': scipy.sparse.linalg.lgmres,
}

def linear_solve(A_csr, b, method='spsolve', tol=1e-10, maxiter=1000, precond=True):
    """
    統一的線性求解入口
    method: 'spsolve' | 'gmres' | 'bicgstab' | 'cgs' | 'lgmres'
    """
    method = method.lower()
    if method == 'spsolve' or method == 'lu':
        return scipy.sparse.linalg.spsolve(A_csr, b), 'spsolve'

    solver_fn = ITERATIVE_SOLVERS.get(method)
    if solver_fn is None:
        # fallback to spsolve for unknown methods
        return scipy.sparse.linalg.spsolve(A_csr, b), 'spsolve'

    # 預處理器 (ILU preconditioner) — 大幅加速迭代收斂
    M = None
    if precond:
        try:
            ilu = scipy.sparse.linalg.spilu(A_csr.tocsc(), drop_tol=1e-4)
            M = scipy.sparse.linalg.LinearOperator(A_csr.shape, ilu.solve)
        except Exception:
            M = None

    x, info = solver_fn(A_csr, b, tol=tol, maxiter=maxiter, M=M)
    if info != 0:
        # 迭代法不收斂 → 自動 fallback 到直接法
        x = scipy.sparse.linalg.spsolve(A_csr, b)
        return x, f'{method}→spsolve'
    return x, method


class SimulatorOptions:
    """
    .OPTIONS 控制參數 — 從 netlist 解析傳入
    支援: METHOD, SOLVER, RELTOL, ABSTOL, ITL1, ITL4, GMIN, SRCSTEPS
    """
    def __init__(self, options_dict=None):
        opts = options_dict or {}
        # NR 收斂
        self.reltol = float(opts.get('RELTOL', 1e-3))
        self.abstol = float(opts.get('ABSTOL', 1e-6))
        self.itl1 = int(opts.get('ITL1', 100))      # OP 最大 NR 迭代
        self.itl4 = int(opts.get('ITL4', 100))       # TRAN 每步最大 NR 迭代
        self.gmin = float(opts.get('GMIN', 1e-12))   # 最小電導
        # 線性求解器
        self.solver = str(opts.get('SOLVER', 'spsolve')).lower()
        # 時間積分法: BE (Backward Euler), TRAP (Trapezoidal), GEAR2 (BDF-2)
        self.method = str(opts.get('METHOD', 'TRAP')).upper()
        # Damped NR
        self.damping = str(opts.get('DAMPING', 'AUTO')).upper()  # AUTO, ON, OFF
        # Source stepping (NR 不收斂時的後備)
        self.srcsteps = int(opts.get('SRCSTEPS', 0))  # 0=auto, >0=固定步數


class Simulator:
    """
    NextSPICE 分析驅動引擎 (v0.5 - Multi-Solver Edition)
    支援:
      - 線性求解: spsolve / GMRES / BiCGSTAB / CGS / LGMRES
      - 時間積分: Backward Euler / Trapezoidal / Gear-2 (BDF-2)
      - NR 改良: Damped Newton-Raphson + Source Stepping fallback
    """
    def __init__(self, circuit, options=None):
        self.circuit = circuit
        self.node_mgr = circuit.node_mgr
        self.dim = 0
        self.extra_var_map = {}
        self.extra_by_name = {}
        self.opts = options if isinstance(options, SimulatorOptions) else SimulatorOptions(options)

    def _make_ctx(self, mode, freq=None, t=None, dt=None):
        return {
            'mode': mode,
            'freq': freq,
            't': t,
            'dt': dt,
            'extra_map': self.extra_var_map,
            'extra_by_name': self.extra_by_name
        }

    def _prepare_mna_structure(self):
        node_count = self.node_mgr.num_unknowns
        curr_extra_idx = node_count
        self.extra_var_map = {}
        for el in self.circuit.elements:
            if el.extra_vars > 0:
                self.extra_var_map[el] = curr_extra_idx
                curr_extra_idx += el.extra_vars
        
        self.dim = curr_extra_idx
        self.extra_by_name = {el.name.upper(): idx for el, idx in self.extra_var_map.items()}
        return self.dim

    def _stamp_system(self, A, b, ctx, x_guess=None):
        """統一蓋章入口 — 線性 + 非線性元件"""
        if x_guess is not None:
            ctx['current_x'] = x_guess
        for el in self.circuit.elements:
            extra_idx = self.extra_var_map.get(el)
            if getattr(el, 'is_nonlinear', False):
                el.stamp_nonlinear(A, b, x_guess, self.node_mgr.mapping)
            else:
                el.stamp(A, b, extra_idx=extra_idx, ctx=ctx)

    def _linear_solve(self, A, b):
        """統一的線性求解包裝"""
        A_csr = A.tocsr()
        x, method_used = linear_solve(A_csr, b, method=self.opts.solver)
        return x, A_csr, method_used

    def _nr_loop(self, dim, ctx, max_iters, reltol, abstol, x_init=None, damping='AUTO'):
        """
        通用 Newton-Raphson 迴圈，支援 Damped NR
        damping: 'OFF' = 標準 NR, 'ON' = 永遠阻尼, 'AUTO' = 發散時自動啟用
        """
        x_guess = x_init if x_init is not None else np.zeros(dim, dtype=np.float64)
        prev_norm = float('inf')
        method_used = ''

        for i in range(max_iters):
            A = scipy.sparse.lil_matrix((dim, dim), dtype=np.float64)
            b = np.zeros(dim, dtype=np.float64)
            self._stamp_system(A, b, ctx, x_guess)

            try:
                x_new, A_csr, method_used = self._linear_solve(A, b)
            except Exception as e:
                return None, A_csr if 'A_csr' in dir() else None, str(e), method_used

            # Damped NR: 如果更新量太大，縮小步長
            diff = x_new - x_guess
            diff_norm = np.linalg.norm(diff)

            if damping == 'ON' or (damping == 'AUTO' and diff_norm > prev_norm * 2):
                # 自適應阻尼因子: 越發散越保守
                alpha = min(1.0, prev_norm / (diff_norm + 1e-30))
                alpha = max(alpha, 0.1)  # 最小 10% 步長
                x_new = x_guess + alpha * diff

            prev_norm = diff_norm

            # 收斂檢查
            conv_diff = np.abs(x_new - x_guess)
            tolerance = reltol * np.maximum(np.abs(x_new), np.abs(x_guess)) + abstol
            if np.all(conv_diff <= tolerance):
                residual = np.max(np.abs(A_csr.dot(x_new) - b))
                return x_new, residual, None, method_used

            x_guess = x_new

        return None, None, f"NR failed to converge after {max_iters} iterations", method_used

    def solve_op(self, ctx=None, max_iters=None, reltol=None, abstol=None):
        """
        DC 工作點求解器 — 支援 Damped NR + Source Stepping fallback
        """
        dim = self._prepare_mna_structure()
        if dim == 0:
            return SolverResult(status="EMPTY", error_msg="No unknown variables.")

        if ctx is None:
            ctx = self._make_ctx(mode='op')
        max_iters = max_iters or self.opts.itl1
        reltol = reltol or self.opts.reltol
        abstol = abstol or self.opts.abstol

        start_t = time.time()

        # 第一輪：標準 / Damped NR
        x, residual, err, method_used = self._nr_loop(
            dim, ctx, max_iters, reltol, abstol, damping=self.opts.damping)

        if x is not None:
            return SolverResult(x=x, residual=residual,
                                solve_time=time.time() - start_t, method_used=method_used)

        # 第二輪：Source Stepping (漸進增大源值以幫助收斂)
        src_steps = self.opts.srcsteps if self.opts.srcsteps > 0 else 10
        saved_sources = {}
        for el in self.circuit.elements:
            if hasattr(el, 'dc_value'):
                saved_sources[el] = el.dc_value
            elif hasattr(el, 'value') and el.name.upper().startswith(('V', 'I')):
                saved_sources[el] = el.value

        x_guess = np.zeros(dim, dtype=np.float64)
        src_success = False

        try:
            for step in range(1, src_steps + 1):
                scale = step / src_steps
                for el, orig in saved_sources.items():
                    if hasattr(el, 'dc_value'):
                        el.dc_value = orig * scale
                    elif hasattr(el, 'value'):
                        el.value = orig * scale

                x_step, res_step, err_step, m = self._nr_loop(
                    dim, ctx, max_iters, reltol, abstol, x_init=x_guess, damping='ON')

                if x_step is not None:
                    x_guess = x_step
                    method_used = f'srcstep({step}/{src_steps})+{m}'
                    if step == src_steps:
                        src_success = True
                else:
                    break
        finally:
            # 復原所有源值
            for el, orig in saved_sources.items():
                if hasattr(el, 'dc_value'):
                    el.dc_value = orig
                elif hasattr(el, 'value'):
                    el.value = orig

        if src_success:
            residual = res_step
            return SolverResult(x=x_guess, residual=residual,
                                solve_time=time.time() - start_t, method_used=method_used)

        return SolverResult(
            status="NON_CONVERGENCE",
            error_msg=f"OP failed after NR + Source Stepping. Last: {err}",
            solve_time=time.time() - start_t
        )
    def solve_ac(self, f_start, f_stop, points, sweep_type='DEC'):
        dim = self._prepare_mna_structure()
        if dim == 0: return []

        sweep_type = sweep_type.upper()
        if sweep_type == 'DEC':
            decades = math.log10(f_stop / f_start)
            total_points = int(round(points * decades)) + 1
            freqs = np.logspace(np.log10(f_start), np.log10(f_stop), total_points)
        elif sweep_type == 'OCT':
            octaves = math.log2(f_stop / f_start)
            total_points = int(round(points * octaves)) + 1
            freqs = np.logspace(np.log10(f_start), np.log10(f_stop), total_points)
        elif sweep_type == 'LIN':
            freqs = np.linspace(f_start, f_stop, points)
        else: return [{"status": "ERROR", "msg": f"Unsupported AC sweep: {sweep_type}"}]

        ac_results = []
        for f in freqs:
            A_ac = scipy.sparse.lil_matrix((dim, dim), dtype=np.complex128)
            b_ac = np.zeros(dim, dtype=np.complex128)
            ctx = self._make_ctx(mode='ac', freq=f)
            for el in self.circuit.elements:
                extra_idx = self.extra_var_map.get(el)
                el.stamp(A_ac, b_ac, extra_idx=extra_idx, ctx=ctx)
            try:
                A_csr = A_ac.tocsr()
                # AC 的複數矩陣只支援直接法 (spsolve)
                x_ac = scipy.sparse.linalg.spsolve(A_csr, b_ac)
                residual = np.max(np.abs(A_csr.dot(x_ac) - b_ac))
                ac_results.append({"freq": f, "x": x_ac, "status": "SUCCESS", "residual": float(residual)})
            except Exception as e:
                ac_results.append({"freq": f, "x": None, "status": "FAILURE", "error_msg": str(e)})
        return ac_results

    def solve_dc_sweep(self, source_name, start_v, stop_v, step_v):
        source_name = source_name.upper()
        target = next((el for el in self.circuit.elements if el.name.upper() == source_name), None)
        if not target: return [{"status": "ERROR", "msg": f"Source '{source_name}' not found"}]

        sweep_results = []
        original_val = getattr(target, 'dc_value', getattr(target, 'value', 0.0))
        v_points = np.arange(start_v, stop_v + (step_v * 0.1), step_v)
        
        try:
            for v in v_points:
                if hasattr(target, 'dc_value'): target.dc_value = v
                elif hasattr(target, 'value'): target.value = v
                res = self.solve_op() 
                sweep_results.append({"v_in": v, "result": res})
        finally:
            if hasattr(target, 'dc_value'): target.dc_value = original_val
            elif hasattr(target, 'value'): target.value = original_val
            
        return sweep_results
        
    def solve_tran(self, tstep, tstop, max_iters=None, reltol=None, abstol=None):
        """
        暫態求解器 — 支援 Backward Euler / Trapezoidal / Gear-2 (BDF-2)
        時間積分法由 self.opts.method 控制:
          BE   = Backward Euler (一階, 穩定但精度低)
          TRAP = Trapezoidal    (二階, A-stable, 預設)
          GEAR2 = BDF-2         (二階, L-stable, 抗振盪)
        """
        dim = self._prepare_mna_structure()
        if dim == 0: return []

        max_iters = max_iters or self.opts.itl4
        reltol = reltol or self.opts.reltol
        abstol = abstol or self.opts.abstol
        integration = self.opts.method  # BE, TRAP, GEAR2

        results = []
        saved_dc = {}

        # 1. 處理暫態電源的初始 DC 狀態
        for el in self.circuit.elements:
            if hasattr(el, '_eval_tran_voltage') and el.tran:
                saved_dc[el] = el.dc_value
                el.dc_value = el._eval_tran_voltage(0.0)
            elif hasattr(el, '_eval_tran_current') and el.tran:
                saved_dc[el] = el.dc_value
                el.dc_value = el._eval_tran_current(0.0)

        # 2. Initial OP
        try:
            op_res = self.solve_op(ctx=self._make_ctx(mode='op'))
        finally:
            for el, val in saved_dc.items(): el.dc_value = val

        if op_res.status != "SUCCESS":
            return [{"status": "ERROR", "msg": f"Initial OP failed: {op_res.error_msg}"}]

        x_prev = op_res.x
        x_prev2 = None  # Gear-2 需要 t(n-2) 的解
        results.append({"time": 0.0, "x": x_prev.copy(), "status": "SUCCESS"})

        for el in self.circuit.elements:
            if hasattr(el, 'update_history'):
                el.update_history(x_prev, extra_idx=self.extra_var_map.get(el))

        t_points = np.arange(tstep, tstop + (tstep * 0.1), tstep)

        # 對 Gear-2: 第一步強制用 BE（因為還沒有 x(n-2)）
        first_step = True

        # 3. 時間推進
        for t in t_points:
            x_guess = x_prev.copy()
            converged = False

            # 決定這一步的積分法
            if integration == 'GEAR2' and first_step:
                step_method = 'be'  # Gear-2 第一步退化為 BE
            elif integration == 'GEAR2':
                step_method = 'gear2'
            elif integration == 'BE':
                step_method = 'be'
            else:
                step_method = 'trapezoidal'

            for i in range(max_iters):
                A = scipy.sparse.lil_matrix((dim, dim), dtype=np.float64)
                b = np.zeros(dim, dtype=np.float64)

                ctx = self._make_ctx(mode='tran', t=t, dt=tstep)
                ctx['current_x'] = x_guess
                ctx['integration'] = step_method

                # Gear-2 需要額外的歷史資訊
                if step_method == 'gear2':
                    ctx['x_prev'] = x_prev
                    ctx['x_prev2'] = x_prev2

                self._stamp_system(A, b, ctx, x_guess)

                try:
                    x_new, A_csr, _ = self._linear_solve(A, b)
                except Exception as e:
                    results.append({"time": t, "status": "FAILURE", "msg": f"Matrix singular: {str(e)}"})
                    return results

                # Damped NR for tran
                if self.opts.damping != 'OFF':
                    diff_vec = x_new - x_guess
                    diff_norm = np.linalg.norm(diff_vec)
                    if i > 0 and diff_norm > prev_diff_norm * 2:
                        alpha = min(1.0, prev_diff_norm / (diff_norm + 1e-30))
                        alpha = max(alpha, 0.1)
                        x_new = x_guess + alpha * diff_vec
                    prev_diff_norm = diff_norm
                else:
                    if i == 0:
                        prev_diff_norm = np.linalg.norm(x_new - x_guess)

                conv_diff = np.abs(x_new - x_guess)
                tolerance = reltol * np.maximum(np.abs(x_new), np.abs(x_guess)) + abstol
                if np.all(conv_diff <= tolerance):
                    converged = True
                    break

                x_guess = x_new

            if not converged:
                results.append({"time": t, "status": "FAILURE",
                                "msg": f"TRAN NR failed at t={t*1000:.2f}ms ({step_method})"})
                break

            results.append({"time": t, "x": x_new.copy(), "status": "SUCCESS"})

            for el in self.circuit.elements:
                if hasattr(el, 'update_history'):
                    el.update_history(x_new, extra_idx=self.extra_var_map.get(el),
                                      dt=tstep, integration=step_method)

            x_prev2 = x_prev
            x_prev = x_new
            first_step = False

        return results

    def get_full_report(self, solution_vec):
        if solution_vec is None: return {}
        report = self.circuit.get_voltage_report(solution_vec)
        for el, idx in self.extra_var_map.items():
            if idx < len(solution_vec):
                report[f"I({el.name})"] = solution_vec[idx]
        return report
    def _get_element_by_name(self, name):
        """安全獲取元件，統一轉大寫比對"""
        name = str(name).upper().strip()
        return next((el for el in self.circuit.elements if el.name.upper() == name), None)

    def _resolve_voltage_index(self, node_name):
        """
        絕對安全的節點解析器
        回傳: index (供 op_res.x 使用), 或 -1 (代表接地), 或 None (找不到)
        """
        # 過濾 V() 括號並轉大寫
        clean_name = str(node_name).upper().replace("V(", "").replace(")", "").strip()
        
        if clean_name in ["0", "GND"]:
            return -1  # 接地節點電壓永遠為 0，不在未知數向量中

        idx = self.circuit.node_mgr.mapping.get(clean_name)
        if idx is None or idx == 0:
            return None
            
        return idx - 1

    def _get_param_value(self, el, attr_name=None):
        """智慧屬性提取器，支援動態命名"""
        if attr_name and hasattr(el, attr_name):
            return getattr(el, attr_name)
        # Fallback heuristic
        if hasattr(el, 'value'): return el.value
        if hasattr(el, 'dc_value'): return el.dc_value
        return None

    def _set_param_value(self, el, val, attr_name=None):
        """智慧屬性注入器"""
        if attr_name and hasattr(el, attr_name):
            setattr(el, attr_name, val)
        elif hasattr(el, 'value'):
            el.value = val
        elif hasattr(el, 'dc_value'):
            el.dc_value = val

    def measure_dc_gain(self, out_idx, in_src_name):
        """封裝單次 OP 與 Gain 計算，確保輸入擾動時分母也能動態更新"""
        # 強制清除 MNA 快取，確保微擾生效
        if hasattr(self, 'last_A'): self.last_A = None 
        
        op_res = self.solve_op()
        if op_res.status != "SUCCESS": 
            return None

        # 處理輸出電壓 (如果是接地則為 0)
        out_v = 0.0 if out_idx == -1 else op_res.x[out_idx]

        # 動態獲取當下的輸入電壓 (解決 Risk: Input perturbation)
        in_el = self._get_element_by_name(in_src_name)
        in_v = self._get_param_value(in_el)
        
        if in_v is None or in_v == 0:
            return None # 避免 Division by Zero

        return out_v / in_v

    def solve_sens_perturbation(self, out_node, in_src_name, targets, rel_step=1e-5, min_step=1e-12):
        """
        工業級微擾靈敏度分析 (Central Difference Edition)
        - 支援 tuple targets: [("R1", "value"), ("V1", "dc_value"), "R2"]
        """
        out_idx = self._resolve_voltage_index(out_node)
        if out_idx is None:
            return {"status": "ERROR", "message": f"Output node '{out_node}' is invalid or not found."}

        in_el = self._get_element_by_name(in_src_name)
        if not in_el:
            return {"status": "ERROR", "message": f"Input source '{in_src_name}' not found."}

        # 1. 基準測試 (Base Run)
        base_gain = self.measure_dc_gain(out_idx, in_src_name)
        if base_gain is None:
            return {"status": "ERROR", "message": "Failed to calculate base DC gain. OP may not converge or input is 0."}

        results = {}

        # 2. 開始中央差分微擾
        for target in targets:
            # 支援彈性 Target 格式：字串 "R1" 或 Tuple ("M1", "gm")
            if isinstance(target, tuple):
                el_name, attr_name = target
            else:
                el_name, attr_name = str(target), None

            el = self._get_element_by_name(el_name)
            if not el:
                results[el_name] = {"status": "ERROR", "message": "Element not found"}
                continue

            old_value = self._get_param_value(el, attr_name)
            if old_value is None:
                results[el_name] = {"status": "ERROR", "message": "Parameter unsupported"}
                continue

            # 防呆：動態計算步長，加上底線保護避免被浮點數誤差吃掉
            delta = max(abs(old_value) * rel_step, min_step)

            # --- Central Difference 核心 ---
            # 正向微擾 (+Delta)
            self._set_param_value(el, old_value + delta, attr_name)
            gain_plus = self.measure_dc_gain(out_idx, in_src_name)

            # 反向微擾 (-Delta)
            self._set_param_value(el, old_value - delta, attr_name)
            gain_minus = self.measure_dc_gain(out_idx, in_src_name)

            # 🚨 鐵律：立刻復原元件數值
            self._set_param_value(el, old_value, attr_name)
            if hasattr(self, 'last_A'): self.last_A = None

            if gain_plus is None or gain_minus is None:
                results[el_name] = {"status": "ERROR", "message": "OP failed during perturbation"}
                continue

            # 計算中央差分靈敏度
            sens = (gain_plus - gain_minus) / (2 * delta)
            norm_sens = (old_value / base_gain) * sens if base_gain != 0 else 0.0

            results[el_name] = {
                "status": "SUCCESS",
                "param_tested": attr_name or "default_value",
                "absolute": sens,
                "normalized": norm_sens
            }

        return {
            "status": "SUCCESS",
            "base_gain": base_gain,
            "sensitivities": results
        }



    def solve_tf(self, out_node_str, in_src_name):
        """
        計算小信號轉移函數 (.TF)
        包含: DC Gain, Input Resistance, Output Resistance
        """
        out_node = out_node_str.upper().replace("V(", "").replace(")", "").strip()
        in_src_name = in_src_name.upper()

        # 1. 先求出直流工作點 (DC OP)，讓所有非線性元件 (如二極體) 的斜率固定
        op_res = self.solve_op()
        if op_res.status != "SUCCESS":
            return {"status": "ERROR", "message": "DC OP failed, cannot run .TF"}

        # 找出目標節點與輸入電源的 index
        out_idx = self.circuit.node_mgr.mapping.get(out_node, 0) - 1
        
        in_src = next((e for e in self.circuit.elements if e.name.upper() == in_src_name), None)
        if not in_src:
            return {"status": "ERROR", "message": f"Source {in_src_name} not found"}
            
        in_src_idx = self.extra_map.get(in_src)

        n = self.n_nodes + self.n_extra
        # 準備空矩陣，用剛剛收斂的 x (op_res.x) 重新蓋章，取得小信號 Jacobian
        A = np.zeros((n, n))
        b_zero = np.zeros(n)
        
        ctx = self._make_ctx(mode='op')
        for el in self.circuit.elements:
            if getattr(el, 'is_nonlinear', False):
                el.stamp_nonlinear(op_res.x, A, b_zero, extra_idx=self.extra_map.get(el), ctx=ctx)
            else:
                el.stamp(A, b_zero, extra_idx=self.extra_map.get(el), ctx=ctx)

        # ---------------------------------------------------
        # 計算 1: Gain 與 Input Resistance
        # 把所有獨立電源的 RHS 設為 0，只把 in_src 設為 1V / 1A
        # ---------------------------------------------------
        b_gain = np.zeros(n)
        if in_src.name.upper().startswith('V'):
            b_gain[in_src_idx] = 1.0  # 1V 測試電壓
        elif in_src.name.upper().startswith('I'):
            if in_src.n1 > 0: b_gain[in_src.n1 - 1] -= 1.0
            if in_src.n2 > 0: b_gain[in_src.n2 - 1] += 1.0

        try:
            x_gain = np.linalg.solve(A, b_gain)
            gain = x_gain[out_idx] if out_idx >= 0 else 0.0
            
            if in_src.name.upper().startswith('V'):
                i_in = x_gain[in_src_idx]
                rin = 1.0 / abs(i_in) if abs(i_in) > 1e-15 else float('inf')
            else:
                v_in = (x_gain[in_src.n1-1] if in_src.n1 > 0 else 0) - (x_gain[in_src.n2-1] if in_src.n2 > 0 else 0)
                rin = abs(v_in) / 1.0
        except Exception as e:
            return {"status": "ERROR", "message": f"Gain computation failed: {e}"}

        # ---------------------------------------------------
        # 計算 2: Output Resistance
        # 關閉所有獨立電源，在 out_node 注入 1A 測試電流
        # ---------------------------------------------------
        b_rout = np.zeros(n)
        if out_idx >= 0:
            b_rout[out_idx] -= 1.0  # 從 out_node 抽出 1A (相當於灌入 1A 測試電流，方向取決於定義)
            
        try:
            x_rout = np.linalg.solve(A, b_rout)
            # Rout = 測試節點的電壓變化 / 1A
            rout = abs(x_rout[out_idx]) if out_idx >= 0 else 0.0
        except:
            rout = float('inf')

        return {
            "status": "SUCCESS",
            "gain": gain,
            "rin": rin,
            "rout": rout,
            "out_node": out_node,
            "in_src": in_src_name
        }