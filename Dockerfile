FROM python:3.11-slim-buster
# Instala las herramientas de compilación necesarias
RUN apt-get update && apt-get install -y \
    build-essential \
    make \
    gcc \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Establece el directorio de trabajo
WORKDIR /app

# Copia los archivos de requisitos primero para aprovechar la caché de Docker
COPY requirements.txt .

# Instala las dependencias de Python
RUN pip install --no-cache-dir -r requirements.txt

# Copia el resto del código de la aplicación
COPY . .

# Comando para ejecutar la aplicación
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8010"]
