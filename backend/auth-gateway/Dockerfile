FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY auth_gateway.py .

EXPOSE 8020

CMD ["python", "auth_gateway.py"]
