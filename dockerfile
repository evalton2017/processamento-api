FROM python:3.12-slim

# 1. Instalação das dependências nativas, GIS, OCR e dependências do WebKit
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
    fontconfig \
    fonts-dejavu-core \
    wget \
    ca-certificates \
    libxrender1 \
    libxext6 \
    libfontconfig1 \
    libx11-6 \
    libxcb1 \
    libxau6 \
    libxdmcp6 \
    libbsd0 \
    libmd0 \
    && rm -rf /var/lib/apt/lists/*

RUN wget --progress=dot:giga https://github.com \
    && dpkg -i wkhtmltox_0.12.6.1-2.bullseye_amd64.deb \
    || apt-get install -y --no-install-recommends -f \
    && rm wkhtmltox_0.12.6.1-2.bullseye_amd64.deb \
    && rm -rf /var/lib/apt/lists/*

# 2. Configuração de variáveis de ambiente para compilação nativa e caches
ENV CPLUS_INCLUDE_PATH=/usr/include/gdal
ENV C_INCLUDE_PATH=/usr/include/gdal
ENV GDAL_CONFIG=/usr/bin/gdal-config
# 🚀 Define uma pasta mutável para o Matplotlib e Contextily guardarem mapas temporários na VPS
ENV MPLCONFIGDIR=/tmp/matplotlib
ENV CONTEXTILY_CACHE=/tmp/contextily

WORKDIR /app

COPY requirements.txt .

# 3. Atualização das ferramentas de pacotes essenciais
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# 4. Instalação segura das dependências Python
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
