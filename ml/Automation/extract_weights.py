"""Extract LogisticRegression weights from cuML-pickled meta_ensemble.joblib"""
import struct

with open('amttp_models_20251231_174617/meta_ensemble.joblib', 'rb') as f:
    data = f.read()

print(f"Total file size: {len(data)} bytes")

# From pickle disassembly:
# - coef_ shape is (8, 1), dtype '<f8' (float64) -> 64 bytes
# - intercept_ shape is (1,), dtype '<f8' -> 8 bytes
# - The raw numpy data is embedded in the pickle stream

# Search for 'data' keyword positions in pickle stream
data_keyword = b'data'
positions = []
idx = 0
while True:
    idx = data.find(data_keyword, idx)
    if idx == -1:
        break
    positions.append(idx)
    idx += 1

print(f"Found 'data' at positions: {positions}")

# Try reading 8 doubles from various offsets to find the coef_ array
print("\n--- Searching for coef_ (8 float64 values) ---")
for pos in range(1320, 1370):
    try:
        vals = struct.unpack('<8d', data[pos:pos+64])
        if all(abs(v) < 100 for v in vals) and any(abs(v) > 0.01 for v in vals):
            print(f"Position {pos}: {[round(v, 10) for v in vals]}")
    except:
        pass

# Search for intercept_
print("\n--- Searching for intercept_ ---")
int_pos = data.find(b'intercept_')
print(f"'intercept_' at position: {int_pos}")
if int_pos > 0:
    for pos in range(int_pos + 10, int_pos + 250):
        try:
            val = struct.unpack('<d', data[pos:pos+8])[0]
            if abs(val) < 100 and abs(val) > 0.001:
                print(f"  Position {pos}: {val}")
        except:
            pass

# Also try to decode the embedded numpy data more carefully
# The pickle uses LONG1 opcode (0x8a) to embed raw bytes
# LONG1 format: 0x8a <1-byte length> <N bytes>
print("\n--- Scanning for LONG1 embedded data ---")
for i in range(len(data) - 2):
    if data[i] == 0x8a:
        length = data[i+1]
        if length > 0:
            raw = data[i+2:i+2+length]
            if length == 64:  # 8 float64s
                vals = struct.unpack('<8d', raw)
                print(f"LONG1 at {i}, len={length}: 8 doubles = {[round(v, 6) for v in vals]}")
            elif length == 8:  # 1 float64
                val = struct.unpack('<d', raw)[0]
                if abs(val) < 100:
                    print(f"LONG1 at {i}, len={length}: 1 double = {val}")
            elif length == 6:
                # Could be an integer or partial data
                # Try interpreting as int
                int_val = int.from_bytes(raw, 'little', signed=True)
                print(f"LONG1 at {i}, len={length}: int = {int_val}, hex = {raw.hex()}")

# The npy format uses a specific header. Let's look for raw float blocks
# by searching for the characteristic 0x0a byte (newline) used as stream separator
print("\n--- Checking around position 1333 (the 0x0a byte) ---")
# The 0x0a at pos 1333 is followed by data. Let's see what's there
for start in [1333, 1334, 1335]:
    if start + 64 <= len(data):
        try:
            vals = struct.unpack('<8d', data[start:start+64])
            print(f"8 doubles from {start}: {[round(v, 6) for v in vals]}")
        except:
            pass

# Check after the 0xff padding 
print("\n--- Checking after 0xff padding ---")
# Find sequence of 0xff bytes near pos 1333
ff_start = 1333
while ff_start < len(data) and data[ff_start] == 0xff:
    ff_start += 1
print(f"0xff padding ends at position {ff_start}")
if ff_start + 64 <= len(data):
    vals = struct.unpack('<8d', data[ff_start:ff_start+64])
    print(f"8 doubles from {ff_start}: {[round(v, 10) for v in vals]}")

# Let's also check the actual bytes starting from 1334
print("\n--- Raw hex around critical area ---")
for offset in [1333, 1334, 1340, 1344]:
    segment = data[offset:offset+8]
    if len(segment) == 8:
        val = struct.unpack('<d', segment)[0]
        print(f"  Pos {offset}: hex={segment.hex()}, float64={val}")
