#!/bin/bash

# Script de inicio para Render.com
echo "Iniciando aplicación Streamlit..."

# Configurar variables de entorno
export STREAMLIT_SERVER_HEADLESS=true
export STREAMLIT_SERVER_RUN_ON_SAVE=false
export STREAMLIT_SERVER_FILE_WATCHER_TYPE=none
export STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

# Ejecutar Streamlit
exec streamlit run streamlit_app.py \
    --server.port=$PORT \
    --server.address=0.0.0.0 \
    --server.headless=true \
    --server.runOnSave=false \
    --server.fileWatcherType=none \
    --server.enableCORS=false \
    --server.enableXsrfProtection=false \
    --browser.gatherUsageStats=false
