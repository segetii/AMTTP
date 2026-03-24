"""Diagnose where system_mode.py stops loading during import."""
import sys, importlib, types

sys.path.insert(0, 'c:/amttp/research/udl')

# Import without __init__.py interference
loader = importlib.machinery.SourceFileLoader(
    'system_mode_test', 'c:/amttp/research/udl/udl/system_mode.py')
spec = importlib.util.spec_from_loader('system_mode_test', loader)
mod = types.ModuleType(spec.name)
mod.__spec__ = spec

try:
    loader.exec_module(mod)
    print("Full load OK")
    print("Has EllipsoidGeometry:", hasattr(mod, 'EllipsoidGeometry'))
    print("Has SystemModeEngine:", hasattr(mod, 'SystemModeEngine'))
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()

# Also try the normal import path
print("\n--- Normal import via udl.system_mode ---")
if 'udl.system_mode' in sys.modules:
    del sys.modules['udl.system_mode']
if 'udl' in sys.modules:
    del sys.modules['udl']

try:
    import udl.system_mode as sm
    print("Has EllipsoidGeometry:", hasattr(sm, 'EllipsoidGeometry'))
    print("Has SystemModeEngine:", hasattr(sm, 'SystemModeEngine'))
    # Find last defined class
    classes = [n for n in dir(sm) if isinstance(getattr(sm, n, None), type)]
    print("Classes found:", classes)
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
