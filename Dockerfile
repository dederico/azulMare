# Usa una imagen ligera de Python
FROM python:3.11-slim

# Establece el directorio de trabajo
WORKDIR /app

# Instala dependencias del sistema necesarias
RUN apt-get update && apt-get install -y \
    build-essential gcc libffi-dev iputils-ping sudo net-tools traceroute wireshark tshark curl procps ffmpeg  \
    && rm -rf /var/lib/apt/lists/*

# Asegurar que el usuario por defecto es root
USER root

# Configurar sudo sin contraseña para root
RUN echo "root ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers

# Habilitar capacidades para acceso a red y ping sin privilegios extra
RUN setcap cap_net_raw,cap_net_admin,cap_sys_admin+ep /bin/ping

# Configurar sysctl para permitir modificaciones de red
RUN echo "net.ipv4.ip_forward=1" >> /etc/sysctl.conf

# Configurar Python para mejor rendimiento
ENV PYTHONUNBUFFERED=1
ENV PYTHONFAULTHANDLER=1
ENV PIP_NO_CACHE_DIR=1

# Copia y instala dependencias de Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia el código de la aplicación
COPY . .

# Copiar y configurar el script de entrada
# Copiar entrypoint.sh al contenedor
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Expone el puerto en el que correrá FastAPI
EXPOSE 8010

# Usa un entrypoint para configuraciones dinámicas
ENTRYPOINT ["/app/entrypoint.sh"]

# Comando por defecto: iniciar Gunicorn con Uvicorn
# CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "-w", "4", "-b", "0.0.0.0:8010", "app.main:app"]
# CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8010"]
CMD ["hypercorn", "app.main:app", "--bind", "0.0.0.0:8010", "--workers", "10"]
