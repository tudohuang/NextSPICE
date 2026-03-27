def parse_directive(item, circuit, diagnostics, eval_func):
    tk = item["tokens"]
    ln = item["line_no"]
    cmd = tk[0].upper()
    
    def log_diag(sev, msg):
        diagnostics.append({"line": ln, "severity": sev, "message": msg})
        
    try:
        if cmd == '.TRAN':
            if len(tk) < 3: raise ValueError(".TRAN requires tstep and tstop")
            circuit["analyses"].append({
                "type": "tran", "tstep": eval_func(tk[1]), "tstop": eval_func(tk[2])
            })
        elif cmd == '.AC':
            if len(tk) < 5: raise ValueError(".AC requires sweep, points, fstart, fstop")
            circuit["analyses"].append({
                "type": "ac", "sweep": tk[1].upper(), "points": int(tk[2]),
                "fstart": eval_func(tk[3]), "fstop": eval_func(tk[4]) 
            })
        elif cmd == '.DC':
            if len(tk) < 5: raise ValueError(".DC requires source, start, stop, step")
            circuit["analyses"].append({
                "type": "dc", "source": tk[1].upper(), "start": eval_func(tk[2]),
                "stop": eval_func(tk[3]), "step": eval_func(tk[4]) 
            })
        elif cmd == '.OP':
            circuit["analyses"].append({"type": "op"})
        elif cmd == '.MODEL':
            if len(tk) < 3: raise ValueError(".MODEL requires name and type")
            circuit["models"].append({
                "name": tk[1].upper(), "type": tk[2].upper(),
                "raw_body": " ".join(tk[3:])
            })
        elif cmd == '.OPTIONS':
            for token in tk[1:]:
                if '=' in token:
                    key, val = token.split('=', 1)
                    try:
                        circuit["options"][key.upper()] = eval_func(val)
                    except:
                        circuit["options"][key.upper()] = val.upper()
                else:
                    circuit["options"][token.upper()] = True
        elif cmd in ['.PRINT', '.PROBE']:
            # 語法範例: .PROBE TRAN V(V_OUT) I(V1)
            if len(tk) >= 3:
                circuit["outputs"].append({
                    "type": cmd[1:], # 會存成 "PRINT" 或 "PROBE"
                    "analysis_type": tk[1].lower(), # 會存成 "tran", "dc", "ac" 等
                    "targets": [t.upper() for t in tk[2:]] # 把要看的變數全部轉大寫存起來
                })
            else:
                diagnostics.append({"line": ln, "severity": "WARNING", "message": f"{cmd} requires analysis type and target variables"})

        elif cmd in ['.MEAS', '.MEASURE']:
            if len(tk) < 4: raise ValueError(".MEASURE requires analysis, name, and expressions")
            circuit["metadata"]["measures"].append({
                "type": "measure", "analysis_type": tk[1].upper(),
                "name": tk[2].upper(), "raw_args": tk[3:]
            })
            
        elif cmd == '.SENS':
            # 語法範例: .SENS V(MID) V1
            if len(tk) < 2: 
                raise ValueError(".SENS requires at least one target variable")
            
            # 🚀 確保存進去的是一個乾淨的陣列，例如 ["V(MID)", "V1"]
            circuit["analyses"].append({
                "type": "sens",
                "targets": [v.upper() for v in tk[1:]] 
            })
        elif cmd == '.STEP':
            # 語法範例: .STEP PARAM R1 1k 10k 2k  或  .STEP R1 1k 10k 2k
            if len(tk) < 5: 
                raise ValueError(".STEP requires target, start, stop, step")
            
            # 判斷有沒有寫 "PARAM" 關鍵字
            if tk[1].upper() == 'PARAM':
                target = tk[2].upper()
                start_idx = 3
            else:
                target = tk[1].upper()
                start_idx = 2
            
            # 將步進設定存入 circuit，作為全域設定
            circuit["step_config"] = {
                "target": target,
                "start": eval_func(tk[start_idx]),
                "stop": eval_func(tk[start_idx+1]),
                "step": eval_func(tk[start_idx+2])
            }

        elif cmd == '.MODEL':
            if len(tk) < 3:
                diagnostics.append({"line": ln, "severity": "ERROR", "message": ".MODEL requires name and type"})
                return
            model_name = tk[1].upper()
            # 有時候 type 和括號會黏在一起，例如 D(IS=...
            raw_type_str = tk[2].upper()
            model_type = raw_type_str.split('(')[0] 
            
            # 把後面的所有 token 組合起來，拔掉括號，找出所有的 key=value
            param_str = " ".join(tk[2:]).upper()
            param_str = param_str[param_str.find(model_type)+len(model_type):].replace('(', ' ').replace(')', ' ')
            
            # 用簡單的 Regex 抓出所有的 KEY=VALUE
            params = {}
            for match in re.finditer(r'([A-Z0-9_]+)\s*=\s*([^\s]+)', param_str):
                key, val_str = match.groups()
                try:
                    # 這裡可以用你原本的 eval_func 解析 1e-14 這種科學記號
                    params[key] = eval_func(val_str) 
                except:
                    params[key] = val_str # 如果不是數字，就存字串
                    
            # 存進藍圖裡！(記得在 Parser __init__ 準備一個 self.circuit["models"] = {})
            if "models" not in circuit:
                circuit["models"] = {}
            circuit["models"][model_name] = {
                "type": model_type,
                "params": params
            }

        else:
            log_diag("INFO", f"Ignored directive: {cmd}")
    except Exception as e:
        log_diag("ERROR", f"Directive {cmd} parse error: {str(e)}")