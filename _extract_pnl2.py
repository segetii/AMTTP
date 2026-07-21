import json, os
base = r"C:\amttp\research\adaptive-friction\pipeline\results"

# v1-v6 performance block
for tag, fname in [
    ("v1","crypto_godmode_v1.json"),("v2","crypto_godmode_v2.json"),
    ("v3","crypto_godmode_v3_alarm_safe.json"),("v4","crypto_godmode_v4_bsignal.json"),
    ("v5","crypto_godmode_v5_regime_bsignal.json"),("v6","crypto_godmode_v6_angular.json"),
]:
    d = json.load(open(os.path.join(base, fname), encoding="utf-8"))
    p = d.get("performance", {})
    best_f, best_c, best_n = 0, 0, "?"
    for k, v in p.items():
        if isinstance(v, dict):
            f = v.get("final_equity", v.get("final", 0))
            c = v.get("calmar", v.get("oos_calmar", 0))
            if f > best_f:
                best_f, best_c, best_n = f, c, k
    print(f"{tag}: final=${best_f:>10,.0f}  calmar={best_c:6.2f}  name={best_n}")

# v7-v8
for tag, fname in [("v7","crypto_godmode_v7_exec_shell.json"),("v8","crypto_godmode_v8_multiasset_shell.json")]:
    d = json.load(open(os.path.join(base, fname), encoding="utf-8"))
    er = d.get("execution_results", [])
    best = max((r for r in er if isinstance(r, dict) and r.get("final")), key=lambda r: r.get("final",0), default={})
    if not best:
        boc = d.get("best_by_oos_calmar", {})
        best = boc if isinstance(boc, dict) and "final" in boc else {}
    print(f"{tag}: final=${best.get('final',0):>10,.0f}  calmar={best.get('calmar',best.get('oos_calmar',0)):6.2f}  name={best.get('name',best.get('variant','?'))}")

# v10
d = json.load(open(os.path.join(base, "crypto_godmode_v10_cluster.json"), encoding="utf-8"))
eq = d.get("equity", {})
best_f, best_n = 0, "?"
for k, v in eq.items():
    f = v.get("final", 0) if isinstance(v, dict) else 0
    if f > best_f:
        best_f, best_n = f, k
cr = d.get("continuous_reference", {})
print(f"v10: final=${best_f:>10,.0f}  cont_ref=${cr.get('final',0):,.0f}  name={best_n}")

# v10b
d = json.load(open(os.path.join(base, "crypto_godmode_v10b_trade_mining.json"), encoding="utf-8"))
print(f"v10b: keys={list(d.keys())}")
for k in d:
    v = d[k]
    if isinstance(v, dict) and "final" in v:
        print(f"  v10b [{k}]: final=${v['final']:,.0f}  calmar={v.get('calmar',0):.2f}")

# v16
d = json.load(open(os.path.join(base, "crypto_godmode_v16_plots.json"), encoding="utf-8"))
m = d.get("metrics", {})
print(f"v16: final=${m.get('final',0):>10,.0f}  calmar={m.get('calmar',0):6.2f}")

# v17
d = json.load(open(os.path.join(base, "crypto_godmode_v17_period_report.json"), encoding="utf-8"))
s = d.get("summary", {})
print(f"v17: final=${s.get('final',0):>10,.0f}  calmar={s.get('calmar',0):6.2f}")

# v18-v24 - scan all json files
all_jsons = [f for f in os.listdir(base) if f.endswith(".json")]
for v in range(18, 25):
    matches = [f for f in all_jsons if f"v{v}_" in f or f"_v{v}_" in f]
    if matches:
        for fname in matches:
            d = json.load(open(os.path.join(base, fname), encoding="utf-8"))
            rs = d.get("results", [])
            if rs:
                best = max((r for r in rs if isinstance(r, dict) and r.get("final")), key=lambda r: r.get("final",0), default={})
                print(f"v{v}: final=${best.get('final',0):>10,.0f}  calmar={best.get('calmar',0):6.2f}  name={best.get('name','?')}")
            else:
                print(f"v{v}: {fname} keys={list(d.keys())[:6]}")
    else:
        print(f"v{v}: NO JSON FOUND")

# v29
d = json.load(open(os.path.join(base, "v29_regularized_validation", "crypto_godmode_v29_regularized_validation.json"), encoding="utf-8"))
sel = d.get("selected", {})
best = sel.get("best_calmar", sel.get("best_final", {}))
if not best:
    rs = d.get("results", [])
    if rs:
        best = max((r for r in rs if isinstance(r, dict) and r.get("final")), key=lambda r: r.get("final",0), default={})
print(f"v29: final=${best.get('final',0):>10,.0f}  calmar={best.get('calmar',0):6.2f}  name={best.get('name','?')}")
