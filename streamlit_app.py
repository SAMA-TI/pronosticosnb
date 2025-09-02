import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from datetime import datetime, timedelta
import requests
import warnings
from urllib3.exceptions import InsecureRequestWarning
import pytz
import time
import math
from datetime import timezone, time
import concurrent.futures
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import urllib.parse

warnings.filterwarnings("ignore", category=InsecureRequestWarning)

# Configuración de la página
st.set_page_config(
    page_title="🌧️ Tablero de estaciones de precipitación",
    page_icon="🌧️",
    layout="wide"
)

# URL del proxy de Cloudflare Workers - REEMPLAZA CON TU URL REAL
CLOUDFLARE_PROXY = "https://sama-api-proxy.scgarzonp.workers.dev"

# Configurar session para requests
def crear_session_requests():
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'es-CO,es;q=0.9,en;q=0.8',
        'Cache-Control': 'max-age=0'
    })
    
    retry_strategy = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        raise_on_status=False
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session

def hacer_request_con_proxy(url, session, timeout=15):
    """Hacer request usando el proxy de Cloudflare"""
    try:
        # Intentar directo primero (para testing local)
        response = session.get(url, verify=False, timeout=5)
        if response.status_code == 200:
            st.info(f"✅ Conexión directa exitosa a {url}")
            return response
    except Exception as e:
        st.warning(f"⚠️ Conexión directa falló: {str(e)}, intentando con proxy...")
    
    # Usar el proxy de Cloudflare
    try:
        encoded_url = urllib.parse.quote(url, safe='')
        proxy_url = f"{CLOUDFLARE_PROXY}?target={encoded_url}"
        st.info(f"🔄 Usando proxy: {proxy_url}")
        
        response = session.get(proxy_url, timeout=timeout)
        st.success(f"✅ Proxy exitoso: Status {response.status_code}")
        return response
    except Exception as e:
        st.error(f"❌ Error con proxy: {str(e)}")
        raise requests.exceptions.RequestException(f"Error con proxy: {str(e)}")

@st.cache_data(ttl=3600)
def cargar_datos():
    """Función para cargar y procesar todos los datos"""
    
    # Estaciones de precipitación (sp) - Solo 3 para testing
    sp_codes = ["101", "102", "103"]
    
    def obtener_datos_estacion(code, calidad=1):
        session = crear_session_requests()
        page = 1
        datos = []
        max_intentos = 2
        
        while page <= 3:  # Limitar páginas para testing
            url = f"https://sigran.antioquia.gov.co/api/v1/estaciones/sp_{code}/precipitacion?calidad={calidad}&page={page}"
            
            st.write(f"🔄 Obteniendo datos de estación {code}, página {page}")
            
            for intento in range(max_intentos):
                try:
                    response = hacer_request_con_proxy(url, session, timeout=15)
                    
                    if response.status_code != 200:
                        st.warning(f"⚠️ Status {response.status_code} para estación {code}")
                        break
                    
                    data = response.json()
                    values = data.get("values", [])
                    
                    if not values:
                        st.info(f"✅ Estación {code}: No más datos en página {page}")
                        return datos
                    
                    datos.extend(values)
                    st.success(f"✅ Estación {code}: {len(values)} registros obtenidos")
                    break
                    
                except Exception as e:
                    st.error(f"🚫 Error estación {code}, intento {intento + 1}: {str(e)}")
                    if intento == max_intentos - 1:
                        return datos
                    time.sleep(2)
            else:
                break
                
            page += 1
            time.sleep(1)
            
        return datos

    def obtener_metadata_sp(code):
        session = crear_session_requests()
        url = f"https://sigran.antioquia.gov.co/api/v1/estaciones/sp_{code}/"
        
        st.write(f"🔄 Obteniendo metadata de estación {code}")
        
        try:
            resp = hacer_request_con_proxy(url, session, timeout=15)
            
            if resp.status_code == 200:
                d = resp.json()
                st.success(f"✅ Metadata {code} obtenida")
                return {
                    "estacion": code,
                    "codigo": d.get("codigo"),
                    "descripcion": d.get("descripcion"),
                    "nombre_web": d.get("nombre_web"),
                    "latitud": float(d.get("latitud", 0)),
                    "longitud": float(d.get("longitud", 0)),
                    "municipio": d.get("municipio"),
                    "region": d.get("region")
                }
            else:
                st.warning(f"⚠️ Metadata {code}: Status {resp.status_code}")
                
        except Exception as e:
            st.error(f"🚫 Error metadata {code}: {str(e)}")
            
        return None

    def procesar_datos(datos, ahora=None):
        if not datos:
            return None

        df = pd.DataFrame(datos)
        df["fecha"] = pd.to_datetime(df["fecha"], utc=True)
        df["muestra"] = pd.to_numeric(df["muestra"], errors='coerce')

        ahora = ahora or datetime.utcnow().replace(tzinfo=pytz.UTC)

        acumulados = {
            "acum_6h": df[(df["fecha"] > ahora - timedelta(hours=6)) & (df["fecha"] <= ahora)]["muestra"].sum(),
            "acum_24h": df[(df["fecha"] > ahora - timedelta(hours=24)) & (df["fecha"] <= ahora)]["muestra"].sum(),
            "acum_72h": df[(df["fecha"] > ahora - timedelta(hours=72)) & (df["fecha"] <= ahora)]["muestra"].sum()
        }

        serie_120h = []
        for h in range(1, 121):
            t_ini = ahora - timedelta(hours=h)
            t_fin = ahora - timedelta(hours=h-1)
            val = df[(df["fecha"] > t_ini) & (df["fecha"] <= t_fin)]["muestra"].sum()
            serie_120h.append({"hora": t_ini, "acumulado": val})

        def acum_dias_meteorologicos(n, df):
            ahora = datetime.now(timezone.utc)
            inicio_meteo = datetime.combine(ahora.date(), time(7, 0, tzinfo=timezone.utc))
            fecha_inicio = inicio_meteo - timedelta(days=n)
            fecha_fin = inicio_meteo
            return df[(df["fecha"] > fecha_inicio) & (df["fecha"] <= fecha_fin)]["muestra"].sum()

        meteo = {
            "ultimo_dia_meteorologico": acum_dias_meteorologicos(1, df),
            "ultimos_7_dias_meteorologicos": acum_dias_meteorologicos(7, df),
            "ultimos_30_dias_meteorologicos": acum_dias_meteorologicos(30, df)
        }

        fecha_max = df["fecha"].max()
        dias_sin_datos = (ahora - fecha_max).days
        datos_recientes = int((ahora - fecha_max) <= timedelta(days=1))

        return {
            **acumulados,
            **meteo,
            "datos_recientes": datos_recientes,
            "dias_sin_datos": dias_sin_datos,
            "fecha_ultimo_dato": fecha_max, 
            "serie_120h": serie_120h
        }

    # Procesar estaciones
    progress_bar = st.progress(0)
    status_text = st.empty()
    resultados = []
    metadata = []

    for i, code in enumerate(sp_codes):
        status_text.text(f'Procesando estación {code}... ({i+1}/{len(sp_codes)})')
        
        datos = obtener_datos_estacion(code)
        
        if datos:
            resumen = procesar_datos(datos)
            meta = obtener_metadata_sp(code)
            
            if resumen and meta:
                resumen["estacion"] = code
                meta.update(resumen)
                resultados.append(resumen)
                metadata.append(meta)
        
        progress_bar.progress((i + 1) / len(sp_codes))
        time.sleep(2)  # Delay entre estaciones

    progress_bar.empty()
    status_text.empty()
    
    if not metadata:
        raise Exception("No se pudieron cargar datos de ninguna estación")

    df_meta = pd.DataFrame(metadata)
    df_meta['municipio'] = 'Sin información'
    
    # Mapear subregiones
    df_meta = df_meta.rename(columns={'region': 'subregion_num'})
    mapa_subregiones = {
        1: 'Valle de Aburra', 2: 'Bajo Cauca', 3: 'Magdalena Medio',
        4: 'Nordeste', 5: 'Norte', 6: 'Oriente',
        7: 'Occidente', 8: 'Suroeste', 9: 'Urabá'
    }
    df_meta['subregion'] = df_meta['subregion_num'].map(mapa_subregiones)

    # Procesar resultados
    df_resultado = pd.DataFrame([{k: v for k, v in r.items() if k != "serie_120h"} for r in resultados])
    df_resultado = df_resultado.sort_values(by=["datos_recientes", "fecha_ultimo_dato"], ascending=[False, False])

    df_pie = df_resultado.copy()
    df_pie['datos_recientes'] = df_pie['datos_recientes'].map({1: 'Reciente', 0: 'No reciente'})

    df_reciente = df_resultado[df_resultado["dias_sin_datos"] < 7].copy()
    df_no_reciente = df_resultado[df_resultado["dias_sin_datos"] >= 7].copy()

    return df_meta, resultados, df_resultado, df_pie, df_reciente, df_no_reciente

# Título principal
st.title("🌧️ Tablero de estaciones de precipitación")

# Mostrar configuración del proxy
st.info(f"🔧 Proxy configurado: {CLOUDFLARE_PROXY}")

# Healthcheck
if st.query_params.get("health") == "check":
    st.write("OK")
    st.stop()

# Test del proxy
if st.query_params.get("test_proxy") == "true":
    st.title("🧪 Test del Proxy de Cloudflare")
    
    session = crear_session_requests()
    test_url = "https://sigran.antioquia.gov.co/api/v1/estaciones/sp_101/"
    
    st.write("Probando conexión con el proxy...")
    
    try:
        response = hacer_request_con_proxy(test_url, session)
        if response.status_code == 200:
            data = response.json()
            st.success("🎉 ¡Proxy funcionando correctamente!")
            st.json(data)
        else:
            st.error(f"❌ Error: Status {response.status_code}")
    except Exception as e:
        st.error(f"❌ Error: {str(e)}")
    
    st.stop()

# Cargar datos
try:
    with st.spinner('Cargando datos de las estaciones...'):
        df_meta, resultados, df_resultado, df_pie, df_reciente, df_no_reciente = cargar_datos()
    
    st.success(f'🎉 Datos cargados exitosamente! {len(df_reciente)} estaciones con datos recientes.')
    
except Exception as e:
    st.error(f"❌ Error al cargar datos: {str(e)}")
    st.info("Para probar el proxy individual, visita: ?test_proxy=true")
    st.stop()

# Mostrar resultados básicos
st.subheader("📊 Resumen de estaciones")

if not df_reciente.empty:
    df_display = df_reciente[["estacion", "acum_6h", "acum_24h", "acum_72h"]].copy()
    df_display["estacion"] = df_display["estacion"].apply(lambda x: f"sp_{x}")
    df_display.columns = ["Estación", "6h", "24h", "72h"]
    st.dataframe(df_display, use_container_width=True)

    # Gráfico simple
    if len(resultados) > 0:
        estacion_ejemplo = resultados[0]
        if "serie_120h" in estacion_ejemplo:
            df_serie = pd.DataFrame(estacion_ejemplo["serie_120h"])
            fig = px.line(df_serie, x="hora", y="acumulado", 
                         title=f"Serie de tiempo - Estación sp_{estacion_ejemplo['estacion']}")
            st.plotly_chart(fig, use_container_width=True)

else:
    st.warning("No hay datos recientes disponibles")

st.sidebar.info(f"Estaciones procesadas: {len(df_meta)}")
