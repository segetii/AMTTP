import urllib.request, json, time

data = json.dumps({
    "from_address": "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",
    "to_address": "0x28C6c06298d514Db089934071355E5743bf21d60",
    "value_eth": 1.5
}).encode()

req = urllib.request.Request(
    "http://localhost:8007/evaluate",
    data=data,
    headers={"Content-Type": "application/json"}
)

t0 = time.time()
resp = urllib.request.urlopen(req, timeout=20)
elapsed = (time.time() - t0) * 1000
result = json.loads(resp.read())

print(f"Status: {resp.status}")
print(f"Wall: {elapsed:.0f}ms")
print(f"Internal: {result.get('processing_time_ms', 0):.0f}ms")
print(f"Action: {result.get('action')}")
print(f"Risk: {result.get('risk_score')}")
print(f"Checks: {len(result.get('checks', []))}")
for c in result.get("checks", []):
    status = "PASS" if c.get("passed") else "FAIL"
    print(f"  {c['service']}: {status} (reason: {c.get('reason', 'n/a')})")
