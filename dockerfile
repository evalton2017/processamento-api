FROM python:3.11-slim

# 1. Instalar apenas o essencial do sistema operacional (se necessário para execução)
RUN apt-get update && apt-get install -y --no-install-recommends \
    binutils \
    libgdal-dev \
    gdal-bin \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 2. Copiar as dependências limpas
COPY requirements.txt .

# 3. Atualizar ferramentas de build básicas e instalar dependências
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# 4. Copiar o restante do código do projeto
COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
