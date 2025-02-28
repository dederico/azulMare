#!/bin/bash

echo "🛠 Iniciando contenedor y configurando permisos..."

# Configurar sysctl para permitir cambios en la red
sysctl -w net.ipv4.ip_forward=1 2>/dev/null || echo "⚠ No se pudo modificar net.ipv4.ip_forward"

# Otorgar permisos para que `ping` pueda ejecutarse sin sudo
chmod +s /bin/ping 2>/dev/null || echo "⚠ No se pudo modificar permisos de ping"

# Verificar que la aplicación está instalada correctamente
if [ ! -f "/app/main.py" ]; then
    echo "❌ ERROR: No se encontró el archivo principal de la aplicación."
    exit 1
fi

echo "✅ Configuración completada. Iniciando la aplicación..."

# Ejecutar el comando que se pasó al contenedor
exec "$@"
