import json
r = json.load(open(r'c:\amttp\results\ercot_prospective_results.json'))
print("=== Raw Engine Prospective Results (no MFLS corrections) ===\n")
print(f"{'Engine':<12} {'AUC':>6} {'FAR%':>6} {'Rec%':>6} {'Prec%':>6} {'TP':>4} {'FP':>4}")
print("-" * 52)
for n, e in r['engines'].items():
    print(f"{n:<12} {e['auc']:6.4f} {e['far']:6.1f} {e['recall']:6.1f} {e['precision']:6.1f} {e['tp']:4d} {e['fp']:4d}")

print("\n=== Per-Event Detail ===")
for n, e in r['engines'].items():
    print(f"\n  {n}:")
    evts = e.get('events', {})
    if isinstance(evts, dict):
        for ev_name, ev_data in evts.items():
            status = ev_data.get('status', '?')
            lead = ev_data.get('lead_weeks', '-')
            print(f"    {ev_name}: status={status}, lead={lead}w")
    elif isinstance(evts, list):
        for ev in evts:
            print(f"    {ev}")
    else:
        print("    (no event detail)")

print("\n=== Thresholds & Timing ===")
for n, e in r['engines'].items():
    thr = e.get('threshold', '?')
    elapsed = e.get('elapsed', '?')
    print(f"  {n}: threshold={thr}, elapsed={elapsed}s")
