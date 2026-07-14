FROM python:3.12-slim

# 1. Instalação das dependências nativas e ferramentas do sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    make \
    binutils \
    gdal-bin \
    libgdal-dev \
    libproj-dev \
    proj-data \
    proj-bin \
    libgeos-dev \
    libgl1 \
    libglib2.0-0 \
    tesseract-ocr \
    pkg-config \
    libexpat1 \
    && rm -rf /var/lib/apt/lists/*

# 2. Configuração de variáveis de ambiente para compilação nativa
ENV CPLUS_INCLUDE_PATH=/usr/include/gdal
ENV C_INCLUDE_PATH=/usr/include/gdal
ENV GDAL_CONFIG=/usr/bin/gdal-config

WORKDIR /app

COPY requirements.txt .

# 3. Atualização das ferramentas de pacotes essenciais
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# 4. Instalação segura das dependências Python
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
