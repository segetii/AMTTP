import json
for cert in ['fdic_cert_3510','fdic_cert_3511','fdic_cert_628',
             'fdic_cert_639','fdic_cert_7213','fdic_cert_34264']:
    path = f'research/adaptive-friction/banklevel_enhanced/gsib_cache_real/{cert}.json'
    d = json.load(open(path))
    if isinstance(d, list):
        print(f'{cert}: LIST len={len(d)}  first={str(d[0])[:120]}')
    elif isinstance(d, dict):
        name = d.get('name', d.get('instname', '?'))
        keys = list(d.keys())[:8]
        print(f'{cert}: name={name!r}  keys={keys}')
        if isinstance(d.get('data'), list) and len(d['data']) > 0:
            print(f'   first row: {d["data"][0]}')

