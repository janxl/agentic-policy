FROM python:3.12-slim
WORKDIR /app
# PyTorch from its CPU-only index: the default build pulls several GB of CUDA libraries this machine has no use for.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
