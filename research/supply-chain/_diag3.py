"""Debug: trace what happens during import of udl.system_mode."""
import sys
sys.path.insert(0, 'c:/amttp/research/udl')

# Remove any cached modules
for key in list(sys.modules.keys()):
    if key.startswith('udl'):
        del sys.modules[key]

import udl.system_mode as sm

# Check last classes defined
classes = [(n, type(getattr(sm, n))) for n in dir(sm) if isinstance(getattr(sm, n, None), type)]
print(f"Total classes: {len(classes)}")
for name, cls_type in sorted(classes):
    print(f"  {name}")

print(f"\nHas EllipsoidGeometry: {hasattr(sm, 'EllipsoidGeometry')}")
print(f"Has SystemModeEngine: {hasattr(sm, 'SystemModeEngine')}")

# Check the actual file after import
lines_in_file = len(open(sm.__file__, encoding='utf-8').readlines())
print(f"\nFile on disk has {lines_in_file} lines")

# Search for EllipsoidGeometry in file
with open(sm.__file__, encoding='utf-8') as f:
    for i, line in enumerate(f, 1):
        if 'class EllipsoidGeometry' in line:
            print(f"Found 'class EllipsoidGeometry' at line {i}")
            break
    else:
        print("'class EllipsoidGeometry' NOT FOUND in file on disk!")
