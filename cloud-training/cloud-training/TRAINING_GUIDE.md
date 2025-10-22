# AMTTP Cloud Training Guide

## Quick Start

### 1. Download Datasets Locally
```bash
cd cloud-training/data
python download_datasets.py
```

### 2. Upload to Google Colab
1. Open Google Colab Pro
2. Upload `02_tabnet_training.ipynb`
3. Upload your processed dataset
4. Run all cells to train TabNet model

### 3. Download Trained Model
1. Download model files from Google Drive
2. Copy to `cloud-training/models/cloud/`
3. Update file IDs in `.env`

### 4. Start Risk Engine
```bash
docker-compose up risk-engine
```

### 5. Test API
```bash
curl -X POST http://localhost:8001/score \
  -H "Content-Type: application/json" \
  -d '{"amount": 500, "hour": 15, "merchant_category": "online"}'
```

## Cost Breakdown

- Google Colab Pro: $10/month
- Training time: 2-3 hours/week
- Total monthly cost: ~$10

## Model Performance Targets

- TabNet Accuracy: >92%
- AUC Score: >0.95
- Inference time: <200ms
- Model size: <50MB

## Troubleshooting

### Model Not Loading
1. Check file IDs in `.env`
2. Verify model format
3. Check logs: `docker logs amttp-risk-engine-1`

### Poor Performance
1. Retrain with more data
2. Adjust hyperparameters
3. Check feature engineering

### API Errors
1. Check Docker logs
2. Verify environment variables
3. Test health endpoint: `/health`
