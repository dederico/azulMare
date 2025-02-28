#!/bin/bash

echo "🛠 Iniciando contenedor y configurando permisos..."

# Otorgar permisos para que `ping` pueda ejecutarse sin sudo
chmod +s /bin/ping 2>/dev/null || echo "⚠ No se pudo modificar permisos de ping"

# Verificar que la aplicación está instalada correctamente
if [ ! -f "/app/main.py" ] && [ ! -f "/app/app/main.py" ]; then
    echo "❌ ERROR: No se encontró el archivo principal de la aplicación en /app o /app/app"
    ls -l /app  # Mostrar el contenido del directorio para depuración
    exit 1
fi

echo "✅ Configuración completada. Iniciando la aplicación..."

# Ejecutar el comando que se pasó al contenedor
exec "$@"