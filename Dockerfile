FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# The embedding model is baked into the image, so `docker compose up` is the whole install and the copied
# folder needs no models/. It lives in /models, outside the bind-mounted /app. Keep the name in sync with gold.MODEL.
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('jinaai/jina-embeddings-v2-base-de', cache_dir='/models')"
ENV MODEL_DIR=/models HF_HUB_OFFLINE=1 PYTHONUNBUFFERED=1
COPY app.py gold.py parse.py ./
COPY static static
EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
