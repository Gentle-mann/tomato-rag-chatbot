FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for Japanese NLP and PDF processing
RUN apt-get update && apt-get install -y \
    build-essential \
    mecab \
    libmecab-dev \
    mecab-ipadic-utf8 \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download Japanese dictionary for fugashi
RUN python -c "import unidic_lite"

# Copy application code
COPY . .

# Create data directory
RUN mkdir -p /app/data/pdfs /app/data/processed

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
