# AMTTP ML Pipeline

> Clean, modular machine learning automation for blockchain fraud detection.

## 📁 Directory Structure

```
ml_pipeline/
├── __init__.py
├── config/
│   ├── __init__.py
│   └── settings.py          # Dataclass-based configuration
├── configs/
│   ├── default.yaml          # Default GPU config
│   ├── colab.yaml            # Google Colab optimized
│   └── cpu.yaml              # CPU-only config
├── data/
│   ├── __init__.py
│   ├── loader.py             # Data loading (cuDF/pandas)
│   ├── preprocessor.py       # Feature encoding & imputation
│   └── splitter.py           # Train/val/test splitting
├── models/
│   ├── __init__.py
│   ├── xgboost_model.py      # XGBoost GPU wrapper
│   ├── autoencoder.py        # PyTorch autoencoder
│   ├── tabnet_model.py       # TabNet wrapper
│   ├── cuml_models.py        # cuML LogReg & RF
│   └── meta_learner.py       # Stacking ensemble
├── training/
│   ├── __init__.py
│   ├── trainer.py            # Unified trainer
│   └── evaluator.py          # Metrics computation
├── scripts/
│   ├── train.py              # CLI training script
│   └── predict.py            # CLI inference script
├── requirements.txt          # GPU dependencies
├── requirements-cpu.txt      # CPU dependencies
└── README.md                 # This file
```

## 🚀 Quick Start

### Installation

```bash
# GPU (Colab or CUDA system)
pip install -r requirements.txt

# CPU only
pip install -r requirements-cpu.txt
```

### Training

```python
from ml_pipeline.config import Settings
from ml_pipeline.training import Trainer, Evaluator

# Load configuration
settings = Settings.from_yaml("configs/default.yaml")

# Initialize trainer
trainer = Trainer(settings)

# Train all models
trainer.train_all(
    dataset_path="data/processed/merged_clean_unified.parquet",
    models=["xgboost", "autoencoder", "tabnet", "cuml", "meta_learner"]
)

# Evaluate
evaluator = Evaluator()
results = evaluator.evaluate_all(
    trainer.y_test.to_numpy(),
    trainer.test_preds
)

# Save models
trainer.save_all("models/")
```

### CLI Usage

```bash
# Train all models
python -m ml_pipeline.scripts.train --config configs/default.yaml --data data/merged.parquet

# Train specific models
python -m ml_pipeline.scripts.train --config configs/colab.yaml --models xgboost autoencoder

# Inference
python -m ml_pipeline.scripts.predict --model models/meta_learner.pkl --input new_data.parquet
```

## 📊 Models

| Model | Type | GPU | Description |
|-------|------|-----|-------------|
| XGBoost | Gradient Boosting | ✅ | Primary classifier with DeviceQuantileDMatrix |
| Autoencoder | Neural Network | ✅ | Anomaly detection via reconstruction error |
| TabNet | Attention-based | ✅ | Interpretable deep learning for tabular data |
| cuML LogReg | Linear | ✅ | GPU logistic regression baseline |
| cuML RF | Ensemble | ✅ | GPU random forest |
| Meta-Learner | Stacking | ❌ | Combines all base models |

## ⚙️ Configuration

Configuration uses YAML files with these sections:

```yaml
# Project settings
project_name: amttp_fraud_detection
use_gpu: true
random_seed: 42

# Data
data:
  dataset_path: data/merged.parquet
  label_col: label_unified
  train_ratio: 0.70

# Model hyperparameters
xgboost:
  max_depth: 6
  learning_rate: 0.1
  n_estimators: 600

autoencoder:
  latent_dim: 32
  epochs: 20

# etc...
```

## 📈 Metrics

Evaluation includes:
- **AUC-ROC**: Area under ROC curve
- **AUC-PR**: Area under precision-recall curve (best for imbalanced data)
- **F1 Score**: Harmonic mean of precision and recall
- **Balanced Accuracy**: Average of sensitivity and specificity
- **Confusion Matrix**: TP, TN, FP, FN counts

## 🔧 Development

```bash
# Run tests
pytest tests/

# Type checking
mypy ml_pipeline/

# Format code
black ml_pipeline/
```

## 📝 License

MIT License - AMTTP Project
