import importlib.util
for m in ['kaggle', 'openml', 'tensorflow_datasets', 'torchvision', 'ucimlrepo', 'requests']:
    spec = importlib.util.find_spec(m)
    print(f"  {m:<25} {'OK' if spec else 'NOT INSTALLED'}")
