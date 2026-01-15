FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for LightGBM
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies including ML libraries
RUN pip install --no-cache-dir \
    fastapi==0.109.0 \
    uvicorn==0.27.0 \
    pydantic==2.5.3 \
    numpy==1.26.4 \
    pandas==2.1.4 \
    scikit-learn==1.4.0 \
    xgboost==2.0.3 \
    lightgbm==4.3.0 \
    joblib==1.3.2

# Copy source code
COPY . /app/

# Expose port
EXPOSE 8000

# Run the service
CMD ["python", "integration_service.py"]
