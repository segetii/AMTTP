"""
Colab Environment Setup for AMTTP Training
Run this in the first cell of your Colab notebook
"""

import subprocess
import sys
import os
from pathlib import Path

def setup_colab_environment():
    """Setup Colab environment for AMTTP training"""
    
    print("🚀 Setting up AMTTP Training Environment in Colab")
    print("=" * 60)
    
    # 1. Install core dependencies
    print("📦 Installing dependencies...")
    dependencies = [
        "pytorch-tabnet",
        "torch-geometric", 
        "pandas",
        "scikit-learn",
        "matplotlib",
        "seaborn",
        "pyyaml",
        "tqdm",
        "optuna",  # For hyperparameter optimization
        "wandb"    # For experiment tracking
    ]
    
    for dep in dependencies:
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", dep, "-q"])
            print(f"  ✅ {dep}")
        except subprocess.CalledProcessError:
            print(f"  ❌ Failed to install {dep}")
    
    # 2. Install PyTorch with CUDA support
    print("\n🔥 Installing PyTorch with CUDA...")
    try:
        subprocess.check_call([
            sys.executable, "-m", "pip", "install",
            "torch", "torchvision", "torchaudio",
            "--index-url", "https://download.pytorch.org/whl/cu118",
            "-q"
        ])
        print("  ✅ PyTorch with CUDA")
    except:
        print("  ❌ Failed to install PyTorch CUDA")
    
    # 3. Mount Google Drive
    print("\n💾 Mounting Google Drive...")
    try:
        from google.colab import drive
        drive.mount('/content/drive')
        print("  ✅ Google Drive mounted")
    except Exception as e:
        print(f"  ❌ Drive mount failed: {e}")
        return False
    
    # 4. Create directory structure
    print("\n📁 Creating directory structure...")
    base_path = "/content/drive/MyDrive/AMTTP_Models"
    directories = [
        f"{base_path}/data",
        f"{base_path}/models/tabnet",
        f"{base_path}/models/gnn", 
        f"{base_path}/logs",
        f"{base_path}/configs",
        f"{base_path}/notebooks"
    ]
    
    for directory in directories:
        os.makedirs(directory, exist_ok=True)
        print(f"  ✅ {directory}")
    
    # 5. Setup logging
    print("\n📝 Configuring logging...")
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(f'{base_path}/logs/training.log'),
            logging.StreamHandler()
        ]
    )
    print("  ✅ Logging configured")
    
    # 6. Check GPU availability
    print("\n🎮 Checking GPU availability...")
    try:
        import torch
        if torch.cuda.is_available():
            gpu_name = torch.cuda.get_device_name(0)
            gpu_memory = torch.cuda.get_device_properties(0).total_memory / 1e9
            print(f"  ✅ GPU: {gpu_name}")
            print(f"  ✅ Memory: {gpu_memory:.1f} GB")
        else:
            print("  ❌ No GPU available")
    except:
        print("  ❌ Failed to check GPU")
    
    # 7. Setup experiment tracking
    print("\n📊 Setting up experiment tracking...")
    try:
        import wandb
        # Initialize wandb (will require login on first run)
        print("  ✅ Weights & Biases available")
        print("  💡 Run 'wandb login' to enable experiment tracking")
    except:
        print("  ❌ Failed to setup wandb")
    
    # 8. Create utility functions
    print("\n🛠️  Creating utility functions...")
    
    # Save configuration
    config_content = """
# AMTTP Training Configuration
project_name: "AMTTP_Risk_Engine"
experiment_name: "fraud_detection_v1"

# Paths
base_path: "/content/drive/MyDrive/AMTTP_Models"
data_path: "data"
models_path: "models"
logs_path: "logs"

# Training settings
random_seed: 42
device: "cuda"
mixed_precision: true
checkpoint_frequency: 10
early_stopping_patience: 15

# Model versioning
version_format: "%Y%m%d_%H%M%S"
keep_best_n_models: 5
"""
    
    with open(f"{base_path}/configs/colab_config.yaml", "w") as f:
        f.write(config_content)
    
    print("  ✅ Configuration saved")
    
    # 9. Create helper functions
    helper_code = '''
def save_model_checkpoint(model, optimizer, epoch, loss, path):
    """Save model checkpoint"""
    torch.save({
        'epoch': epoch,
        'model_state_dict': model.state_dict(),
        'optimizer_state_dict': optimizer.state_dict(),
        'loss': loss,
    }, path)

def load_model_checkpoint(model, optimizer, path):
    """Load model checkpoint"""
    checkpoint = torch.load(path)
    model.load_state_dict(checkpoint['model_state_dict'])
    optimizer.load_state_dict(checkpoint['optimizer_state_dict'])
    return checkpoint['epoch'], checkpoint['loss']

def setup_mixed_precision():
    """Setup mixed precision training"""
    from torch.cuda.amp import GradScaler, autocast
    return GradScaler()

def log_metrics(metrics, step, prefix="train"):
    """Log metrics to wandb and local files"""
    if wandb.run:
        wandb.log({f"{prefix}/{k}": v for k, v in metrics.items()}, step=step)
    
    # Also log to file
    with open(f"{base_path}/logs/metrics.log", "a") as f:
        f.write(f"{step},{prefix},{metrics}\\n")
'''
    
    with open(f"{base_path}/utils.py", "w") as f:
        f.write(helper_code)
    
    print("  ✅ Helper functions created")
    
    print("\n🎉 AMTTP Colab Environment Setup Complete!")
    print("\n📋 Next Steps:")
    print("1. Upload your dataset using files.upload()")
    print("2. Run the training notebook cells")
    print("3. Monitor training progress in the logs")
    print("4. Download trained models to your local setup")
    
    return True

def quick_test():
    """Quick test of the environment"""
    print("\n🧪 Running quick environment test...")
    
    try:
        import torch
        import pandas as pd
        import numpy as np
        from pytorch_tabnet.tab_model import TabNetClassifier
        
        # Test GPU
        device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        x = torch.randn(10, 10).to(device)
        y = torch.matmul(x, x.t())
        
        # Test TabNet
        model = TabNetClassifier()
        
        print("  ✅ All core libraries working")
        print(f"  ✅ Device: {device}")
        return True
        
    except Exception as e:
        print(f"  ❌ Environment test failed: {e}")
        return False

# Auto-run setup when imported
if __name__ == "__main__":
    setup_colab_environment()
    quick_test()
else:
    # Auto-setup when imported in notebook
    setup_colab_environment()

# Colab-specific helper for copying code
def get_notebook_template():
    """Get template code for Colab notebook cells"""
    return '''
# Cell 1: Setup
%run setup_colab.py

# Cell 2: Data Upload
from google.colab import files
uploaded = files.upload()

# Cell 3: Data Preprocessing  
import pandas as pd
import numpy as np

for filename in uploaded.keys():
    df = pd.read_csv(filename)
    print(f"Loaded {filename}: {df.shape}")
    break

# Cell 4: Model Training
from pytorch_tabnet.tab_model import TabNetClassifier
import torch

# Your training code here...

# Cell 5: Model Evaluation
from sklearn.metrics import accuracy_score, roc_auc_score

# Your evaluation code here...

# Cell 6: Save Model
import pickle
from datetime import datetime

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
model_dir = f"/content/drive/MyDrive/AMTTP_Models/models/tabnet/tabnet_{timestamp}"
os.makedirs(model_dir, exist_ok=True)

# Save model and metadata
model.save_model(f"{model_dir}/tabnet_model")
# Save preprocessing components...
'''