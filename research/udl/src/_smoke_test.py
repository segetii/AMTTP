import sys, json, subprocess, os
sys.path.insert(0, 'c:/amttp/research/udl')

env = dict(**os.environ)
env['PYTHONPATH'] = 'c:/amttp/research/udl'
env['PYTHONIOENCODING'] = 'utf-8'
r = subprocess.run(
    [sys.executable, '-u', 'src/worker_eval.py', 'glass'],
    capture_output=True, text=True, timeout=300,
    cwd='c:/amttp/research/udl', env=env, encoding='utf-8', errors='replace'
)
for line in r.stdout.split('\n'):
    if line.startswith('RESULTS_JSON:'):
        data = json.loads(line[len('RESULTS_JSON:'):])
        for k in ['Fisher-lean','QDA-lean','QDA-Mag-lean','BSDT-Fisher','CombA-QDA-Mag']:
            v = data.get(k, {})
            auc = v.get('auc', 0)
            info = v.get('info', '')
            print(f"  {k:<18s} AUC={auc:.4f}  info={info}")
        break
if r.returncode != 0:
    print('FAILED exit:', r.returncode)
    print(r.stderr[-400:])
