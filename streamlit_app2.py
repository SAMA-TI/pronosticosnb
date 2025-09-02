
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

warnings.filterwarnings("ignore", category=InsecureRequestWarning)

# Configuración de la página
st.set_page_config(
    page_title="🌧️ Tablero de estaciones de precipitación",
    page_icon="🌧️",
    layout="wide"
)

# Configurar session para requests con reintentos y headers realistas
def crear_session_requests():
    session = requests.Session()
    
    # Headers que simulan un navegador real
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'es-CO,es;q=0.9,en;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Cache-Control': 'max-age=0'
    })
    
    retry_strategy = Retry(
        total=2,  # Menos reintentos para evitar rate limiting
        backoff_factor=2,  # Mayor tiempo entre reintentos
        status_forcelist=[429, 500, 502, 503, 504],
        raise_on_status=False
    )
    adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=1, pool_maxsize=1)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session

# Función de diagnóstico para logging detallado
def test_conectividad_api():
    """Test de conectividad detallado para diagnóstico"""
    import socket
    import ssl
    
    st.info("🔍 Ejecutando test de conectividad...")
    
    # Test 1: Resolución DNS
    try:
        ip = socket.gethostbyname('sigran.antioquia.gov.co')
        st.success(f"✅ DNS resuelto: sigran.antioquia.gov.co -> {ip}")
    except Exception as e:
        st.error(f"❌ Error DNS: {e}")
        return False
    
    # Test 2: Conexión TCP
    try:
        sock = socket.create_connection(('sigran.antioquia.gov.co', 443), timeout=10)
        sock.close()
        st.success("✅ Conexión TCP establecida en puerto 443")
    except Exception as e:
        st.error(f"❌ Error TCP: {e}")
        return False
    
    # Test 3: Handshake SSL
    try:
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        sock = socket.create_connection(('sigran.antioquia.gov.co', 443), timeout=10)
        ssl_sock = context.wrap_socket(sock, server_hostname='sigran.antioquia.gov.co')
        ssl_sock.close()
        st.success("✅ Handshake SSL exitoso")
    except Exception as e:
        st.error(f"❌ Error SSL: {e}")
        return False
    
    # Test 4: Request HTTP simple
    try:
        session = crear_session_requests()
        url = "https://sigran.antioquia.gov.co/api/v1/estaciones/sp_101/"
        response = session.get(url, verify=False, timeout=15)
        st.success(f"✅ Request HTTP exitoso: Status {response.status_code}")
        return True
    except Exception as e:
        st.error(f"❌ Error HTTP: {e}")
        return False

@st.cache_data(ttl=3600)  # Cache por 1 hora
def cargar_datos():
    """Función para cargar y procesar todos los datos"""

    # Estaciones de precipitación (sp)
    sp_codes = ["101", "102", "103", "104", "106", "108", "109", "131", "132", "133", "134", "135", 
                "136", "137", "138", "139", "140", "141", "142", "143", "144", "145", "146", "147", 
                "149", "150", "151", "152", "154", "155", "156", "157","158","159", "160", "161", "162", "163"]

    def obtener_datos_estacion(code, calidad=1):
        session = crear_session_requests()
        page = 1
        datos = []
        max_intentos = 2
        
        while True:
            url = f"https://sigran.antioquia.gov.co/api/v1/estaciones/sp_{code}/precipitacion?calidad={calidad}&page={page}"
            
            # Log detallado
            st.write(f"🔄 Intentando obtener datos de estación {code}, página {page}")
            
            for intento in range(max_intentos):
                try:
                    # Delay entre requests para evitar rate limiting
                    if intento > 0:
                        time.sleep(3)  # 3 segundos entre reintentos
                    
                    response = session.get(url, verify=False, timeout=15)
                    
                    # Log del response
                    st.write(f"📡 Estación {code}: Status {response.status_code}, Headers: {dict(response.headers)}")
                    
                    if response.status_code == 429:
                        st.warning(f"⏳ Rate limit detectado para estación {code}, esperando...")
                        time.sleep(10)
                        continue
                    
                    if response.status_code != 200:
                        st.warning(f"⚠️ Estación {code}: Status code {response.status_code}")
                        break
                    
                    data = response.json()
                    values = data.get("values", [])
                    if not values:
                        st.info(f"✅ Estación {code}: No más datos disponibles")
                        return datos
                    
                    datos.extend(values)
                    st.success(f"✅ Estación {code}: {len(values)} registros obtenidos (total: {len(datos)})")
                    break
                    
                except requests.exceptions.ConnectTimeout as e:
                    st.error(f"🚫 Timeout de conexión estación {code}, intento {intento + 1}: {str(e)}")
                    if intento == max_intentos - 1:
                        return datos
                except requests.exceptions.ReadTimeout as e:
                    st.error(f"🚫 Timeout de lectura estación {code}, intento {intento + 1}: {str(e)}")
                    if intento == max_intentos - 1:
                        return datos
                except requests.exceptions.RequestException as e:
                    st.error(f"🚫 Error de request estación {code}, intento {intento + 1}: {str(e)}")
                    if intento == max_intentos - 1:
                        return datos
                except Exception as e:
                    st.error(f"🚫 Error inesperado estación {code}, intento {intento + 1}: {str(e)}")
                    if intento == max_intentos - 1:
                        return datos
                
                time.sleep(2)  # Delay entre intentos
            else:
                break
                
            page += 1
            time.sleep(1)  # Delay entre páginas
            
            # Paramos si ya tenemos más de 72 horas de datos
            if datos:
                fechas = [pd.to_datetime(d['fecha']) for d in datos]
                if fechas and (max(fechas) - min(fechas)).total_seconds() > 72 * 3600:
                    break
                    
            # Límite de páginas para evitar loops infinitos
            if page > 10:
                st.warning(f"⚠️ Estación {code}: Límite de páginas alcanzado")
                break
                
        return datos

    def obtener_metadata_sp(code):
        session = crear_session_requests()
        url = f"https://sigran.antioquia.gov.co/api/v1/estaciones/sp_{code}/"
        
        st.write(f"🔄 Obteniendo metadata de estación {code}")
        
        try:
            resp = session.get(url, verify=False, timeout=15)
            st.write(f"📡 Metadata {code}: Status {resp.status_code}")
            
            if resp.status_code == 200:
                d = resp.json()
                st.success(f"✅ Metadata {code}: Obtenida exitosamente")
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
                st.warning(f"⚠️ Metadata {code}: Status code {resp.status_code}")
                
        except requests.exceptions.ConnectTimeout as e:
            st.error(f"🚫 Timeout de conexión metadata {code}: {str(e)}")
        except requests.exceptions.RequestException as e:
            st.error(f"🚫 Error de request metadata {code}: {str(e)}")
        except Exception as e:
            st.error(f"🚫 Error inesperado metadata {code}: {str(e)}")
            
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

        # Serie de 120 horas
        serie_120h = []
        for h in range(1, 121):
            t_ini = ahora - timedelta(hours=h)
            t_fin = ahora - timedelta(hours=h-1)
            val = df[(df["fecha"] > t_ini) & (df["fecha"] <= t_fin)]["muestra"].sum()
            serie_120h.append({"hora": t_ini, "acumulado": val})

        def acum_dias_meteorologicos(n, df):
            # Momento actual en UTC
            ahora = datetime.now(timezone.utc)
            # 7:00 AM UTC del día actual (inicio del día meteorológico actual)
            inicio_meteo = datetime.combine(ahora.date(), time(7, 0, tzinfo=timezone.utc))
            # Rango del día meteorológico: de (hace n días a las 7 AM) hasta (hoy a las 7 AM)
            fecha_inicio = inicio_meteo - timedelta(days=n)
            fecha_fin = inicio_meteo
            # Filtrar y sumar la columna 'muestra' en ese rango
            return df[(df["fecha"] > fecha_inicio) & (df["fecha"] <= fecha_fin)]["muestra"].sum()

        # Diccionario con los acumulados meteorológicos
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

    # Procesar datos con paralelización DESACTIVADA para diagnóstico
    progress_bar = st.progress(0)
    status_text = st.empty()

    resultados = []
    metadata = []
    total_estaciones = len(sp_codes)

    def procesar_estacion(code):
        try:
            st.write(f"🚀 Iniciando procesamiento de estación {code}")
            datos = obtener_datos_estacion(code)
            
            if datos:
                st.write(f"📊 Estación {code}: {len(datos)} registros obtenidos, procesando...")
                resumen = procesar_datos(datos)
            else:
                st.warning(f"⚠️ Estación {code}: Sin datos obtenidos")
                resumen = None
            
            meta = obtener_metadata_sp(code)
            
            if resumen and meta:
                resumen["estacion"] = code
                meta.update(resumen)
                st.success(f"✅ Estación {code}: Procesamiento completado exitosamente")
                return resumen, meta
            else:
                st.error(f"❌ Estación {code}: Falló el procesamiento")
                
        except Exception as e:
            st.error(f"🚫 Error crítico procesando estación {code}: {str(e)}")
        return None, None

    # Procesar estaciones SECUENCIALMENTE para diagnóstico (sin paralelización)
    st.info("🔧 Modo diagnóstico: Procesando estaciones secuencialmente...")
    
    # Solo procesar las primeras 3 estaciones para el test
    sp_codes_test = sp_codes[:3]
    
    for i, code in enumerate(sp_codes_test):
        status_text.text(f'🔍 TEST: Procesando estación {code}... ({i+1}/{len(sp_codes_test)})')
        
        resumen, meta = procesar_estacion(code)
        if resumen and meta:
            resultados.append(resumen)
            metadata.append(meta)
        
        progress_bar.progress((i + 1) / len(sp_codes_test))
        
        # Delay entre estaciones para evitar rate limiting
        if i < len(sp_codes_test) - 1:
            st.info("⏱️ Esperando 5 segundos antes de la siguiente estación...")
            time.sleep(5)

    progress_bar.empty()
    status_text.empty()
    
    if not metadata:
        st.error("❌ No se pudieron obtener datos de ninguna estación en modo test")
        raise Exception("Fallo completo en modo diagnóstico")

    df_meta = pd.DataFrame(metadata)

    # Aplicar correcciones de regiones
    correcciones = {
        'sp_163': 8,
        'sp_149': 3,
        'sp_151': 6,
        'sp_158': 6
    }
    for codigo, region_correcta in correcciones.items():
        df_meta.loc[df_meta['codigo'] == codigo, 'region'] = region_correcta

    # Procesar municipios y subregiones
    try:
        # Buscar el archivo en diferentes ubicaciones posibles
        import os
        possible_paths = [
            'Base de datos estaciones SAMA.xlsx',  # Directorio actual
            '/Users/sergiocamilogarzonperez/Projects/sama/pronosticos/Base de datos estaciones SAMA.xlsx',  # Ruta completa
            '../Base de datos estaciones SAMA.xlsx'  # Directorio padre
        ]

        excel_path = None
        for path in possible_paths:
            if os.path.exists(path):
                excel_path = path
                break

        if excel_path:
            df_excel = pd.read_excel(excel_path, usecols=[
                'GRUPO', 'MUNICIPIO', 'NOM_EST', 'COD_EST', 'TIPO', 'COMUN_PRIORIZ', 'CORRIENTE', 'LAT', 'LONG'
            ])
            df_excel = df_excel[['COD_EST', 'TIPO', 'GRUPO', 'MUNICIPIO', 'NOM_EST', 'COMUN_PRIORIZ', 'CORRIENTE', 'LAT', 'LONG']]
            df_excel['COD_EST'] = df_excel['COD_EST'].astype(str).str.strip().str.lower()

            df_meta = df_meta.rename(columns={'municipio': 'municipio_num'})
            df_municipio = df_excel[['COD_EST', 'MUNICIPIO']].rename(columns={
                'COD_EST': 'codigo',
                'MUNICIPIO': 'municipio'
            })
            df_meta = df_meta.merge(df_municipio, on='codigo', how='left')
            df_meta['municipio'] = df_meta['municipio'].str.capitalize()
            df_meta.loc[df_meta['codigo'] == 'sp_151', 'municipio'] = 'Sonson'
        else:
            st.warning("No se encontró el archivo Excel con datos de municipios. Se usarán datos básicos.")
            df_meta['municipio'] = 'Sin información'
    except Exception as e:
        st.warning(f"Error al cargar archivo Excel: {e}. Se usarán datos básicos.")
        df_meta['municipio'] = 'Sin información'

    # Mapear subregiones
    df_meta = df_meta.rename(columns={'region': 'subregion_num'})
    mapa_subregiones = {
        1: 'Valle de Aburra',
        2: 'Bajo Cauca',
        3: 'Magdalena Medio',
        4: 'Nordeste',
        5: 'Norte',
        6: 'Oriente',
        7: 'Occidente',
        8: 'Suroeste',
        9: 'Urabá'
    }
    df_meta['subregion'] = df_meta['subregion_num'].map(mapa_subregiones)

    # Procesar resultados
    df_resultado = pd.DataFrame([{k: v for k, v in r.items() if k != "serie_120h"} for r in resultados])
    df_resultado = df_resultado.sort_values(by=["datos_recientes", "fecha_ultimo_dato"], ascending=[False, False])

    df_pie = df_resultado.copy()
    df_pie['datos_recientes'] = df_pie['datos_recientes'].map({1: 'Reciente', 0: 'No reciente'})

    df_reciente = df_resultado[df_resultado["dias_sin_datos"] < 7].copy()
    df_reciente = df_reciente.sort_values(by='estacion', ascending=True)

    df_no_reciente = df_resultado[df_resultado["dias_sin_datos"] >= 7].copy()

    return df_meta, resultados, df_resultado, df_pie, df_reciente, df_no_reciente

def cargar_datos_limitado(sp_codes_limitado):
    """Versión simplificada para modo fallback"""
    
    # Usar las mismas funciones internas pero con menos estaciones
    def obtener_datos_estacion(code, calidad=1):
        session = crear_session_requests()
        page = 1
        datos = []
        max_intentos = 2  # Menos intentos en modo fallback
        
        while True:
            url = f"https://sigran.antioquia.gov.co/api/v1/estaciones/sp_{code}/precipitacion?calidad={calidad}&page={page}"
            
            for intento in range(max_intentos):
                try:
                    response = session.get(url, verify=False, timeout=5)  # Timeout menor
                    if response.status_code != 200:
                        break
                    data = response.json()
                    values = data.get("values", [])
                    if not values:
                        return datos
                    datos.extend(values)
                    break
                except Exception:
                    if intento == max_intentos - 1:
                        return datos
                    time.sleep(0.5)
            else:
                break
                
            page += 1
            if len(datos) > 100:  # Limitar datos en modo fallback
                break
        return datos

    def obtener_metadata_sp(code):
        session = crear_session_requests()
        url = f"https://sigran.antioquia.gov.co/api/v1/estaciones/sp_{code}/"
        
        try:
            resp = session.get(url, verify=False, timeout=5)
            if resp.status_code == 200:
                d = resp.json()
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
        except Exception:
            return None
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

    # Procesar estaciones limitadas
    resultados = []
    metadata = []
    
    for code in sp_codes_limitado:
        try:
            datos = obtener_datos_estacion(code)
            resumen = procesar_datos(datos)
            meta = obtener_metadata_sp(code)
            
            if resumen and meta:
                resumen["estacion"] = code
                meta.update(resumen)
                resultados.append(resumen)
                metadata.append(meta)
        except Exception:
            continue

    if not metadata:
        raise Exception("No se pudieron cargar datos de ninguna estación")

    df_meta = pd.DataFrame(metadata)
    df_meta['municipio'] = 'Sin información'
    
    # Mapear subregiones
    df_meta = df_meta.rename(columns={'region': 'subregion_num'})
    mapa_subregiones = {
        1: 'Valle de Aburra',
        2: 'Bajo Cauca',
        3: 'Magdalena Medio',
        4: 'Nordeste',
        5: 'Norte',
        6: 'Oriente',
        7: 'Occidente',
        8: 'Suroeste',
        9: 'Urabá'
    }
    df_meta['subregion'] = df_meta['subregion_num'].map(mapa_subregiones)

    # Procesar resultados
    df_resultado = pd.DataFrame([{k: v for k, v in r.items() if k != "serie_120h"} for r in resultados])
    df_resultado = df_resultado.sort_values(by=["datos_recientes", "fecha_ultimo_dato"], ascending=[False, False])

    df_pie = df_resultado.copy()
    df_pie['datos_recientes'] = df_pie['datos_recientes'].map({1: 'Reciente', 0: 'No reciente'})

    df_reciente = df_resultado[df_resultado["dias_sin_datos"] < 7].copy()
    df_reciente = df_reciente.sort_values(by='estacion', ascending=True)

    df_no_reciente = df_resultado[df_resultado["dias_sin_datos"] >= 7].copy()

    return df_meta, resultados, df_resultado, df_pie, df_reciente, df_no_reciente

# Título principal
st.title("🌧️ Tablero de estaciones de precipitación")

# Agregar un healthcheck simple
if st.query_params.get("health") == "check":
    st.write("OK")
    st.stop()

# Modo de diagnóstico
if st.query_params.get("debug") == "true":
    st.title("🔧 Modo Diagnóstico - Test de Conectividad")
    st.info("Ejecutando tests de conectividad detallados...")
    
    # Test de conectividad
    if test_conectividad_api():
        st.success("🎉 Todos los tests de conectividad pasaron!")
    else:
        st.error("❌ Algunos tests de conectividad fallaron")
    
    st.stop()

# Cargar datos
try:
    with st.spinner('Cargando datos de las estaciones...'):
        df_meta, resultados, df_resultado, df_pie, df_reciente, df_no_reciente = cargar_datos()
    
    if len(resultados) == 0:
        st.error("No se pudieron cargar datos de ninguna estación. Por favor, revisa la conectividad.")
        st.stop()
    
    st.success(f'Datos cargados exitosamente. {len(df_reciente)} estaciones con datos recientes.')
    
except Exception as e:
    st.error(f"Error al cargar datos: {str(e)}")
    st.info("Reintentando cargar datos en modo reducido...")
    
    # Modo fallback con menos estaciones
    try:
        @st.cache_data(ttl=1800)
        def cargar_datos_reducido():
            sp_codes_reducido = ["101", "102", "103", "104", "106"]  # Solo 5 estaciones
            return cargar_datos_limitado(sp_codes_reducido)
        
        df_meta, resultados, df_resultado, df_pie, df_reciente, df_no_reciente = cargar_datos_reducido()
        st.warning("Cargados datos en modo reducido. Algunas estaciones pueden no estar disponibles.")
    except Exception as e2:
        st.error(f"Error crítico: {str(e2)}")
        st.stop()

# Sidebar con filtros
st.sidebar.header("Filtros")

# Filtro por subregión
subregiones = sorted(df_meta["subregion"].dropna().unique())
subregion_seleccionada = st.sidebar.selectbox(
    "Filtrar por subregión:",
    options=["Todas"] + subregiones,
    index=0
)

# Filtro por municipio (dinámico basado en subregión)
if subregion_seleccionada != "Todas":
    municipios = sorted(df_meta[df_meta["subregion"] == subregion_seleccionada]["municipio"].dropna().unique())
else:
    municipios = sorted(df_meta["municipio"].dropna().unique())

municipio_seleccionado = st.sidebar.selectbox(
    "Filtrar por municipio:",
    options=["Todos"] + municipios,
    index=0
)

# Filtro de estaciones (dinámico basado en filtros anteriores)
df_filtrado = df_meta.copy()
if subregion_seleccionada != "Todas":
    df_filtrado = df_filtrado[df_filtrado["subregion"] == subregion_seleccionada]
if municipio_seleccionado != "Todos":
    df_filtrado = df_filtrado[df_filtrado["municipio"] == municipio_seleccionado]

estaciones = sorted(df_filtrado["estacion"].unique())
if estaciones:
    estacion_seleccionada = st.sidebar.selectbox(
        "Selecciona estación:",
        options=[f"sp_{e}" for e in estaciones],
        index=0
    )
else:
    estacion_seleccionada = None
    st.sidebar.warning("No hay estaciones disponibles con los filtros seleccionados")

# Crear columnas para el layout
if estacion_seleccionada:
    col1, col2 = st.columns(2)

    # Serie de tiempo de 120 horas
    with col1:
        st.subheader("Serie de tiempo 120h")
        estacion_id = estacion_seleccionada.replace("sp_", "")
        serie = next((r["serie_120h"] for r in resultados if r["estacion"] == estacion_id), [])
        if serie:
            df_serie = pd.DataFrame(serie)
            fig_serie = px.line(df_serie, x="hora", y="acumulado", 
                              title=f"Serie 120h - {estacion_seleccionada}")
            fig_serie.update_layout(xaxis_title="Hora", yaxis_title="Acumulado (mm)")
            st.plotly_chart(fig_serie, use_container_width=True)
        else:
            st.info("No hay datos disponibles para esta estación")

    # Mapa de ubicación
    with col2:
        st.subheader("📍 Ubicación de la estación")
        estacion_id = estacion_seleccionada.replace("sp_", "")
        fila = df_meta[df_meta["estacion"] == estacion_id]
        if not fila.empty:
            fig_map = px.scatter_map(
                fila,
                lat="latitud",
                lon="longitud",
                hover_name="estacion",
                hover_data=["municipio", "subregion"],
                color_discrete_sequence=["red"],
                zoom=10,
                height=400
            )
            fig_map.update_layout(
                mapbox_style="carto-positron",
                margin={"r": 0, "t": 0, "l": 0, "b": 0},
                showlegend=False
            )
            st.plotly_chart(fig_map, use_container_width=True)
        else:
            st.info("Ubicación no disponible")

# Preparar datos para las tablas con filtros aplicados
df_tabla = df_reciente.merge(df_meta[["estacion", "subregion", "municipio"]], on="estacion", how="left")
if subregion_seleccionada != "Todas":
    df_tabla = df_tabla[df_tabla["subregion"] == subregion_seleccionada]
if municipio_seleccionado != "Todos":
    df_tabla = df_tabla[df_tabla["municipio"] == municipio_seleccionado]

# Tabla de acumulados recientes
st.subheader("Acumulados recientes por estación")
if not df_tabla.empty:
    df_acumulados = df_tabla[["estacion", "acum_6h", "acum_24h", "acum_72h"]].copy()
    df_acumulados["estacion"] = df_acumulados["estacion"].apply(lambda x: f"sp_{x}")
    df_acumulados = df_acumulados.round(3)
    df_acumulados.columns = ["Estación", "Acum. 6h", "Acum. 24h", "Acum. 72h"]

    col1, col2 = st.columns([3, 1])
    with col1:
        st.dataframe(df_acumulados, use_container_width=True)
    with col2:
        csv_acumulados = df_acumulados.to_csv(index=False)
        st.download_button(
            label="📥 Descargar CSV",
            data=csv_acumulados,
            file_name="acumulados_estaciones.csv",
            mime="text/csv"
        )
else:
    st.info("No hay estaciones con datos recientes para los filtros seleccionados")

# Tabla de acumulados meteorológicos
st.subheader("Acumulados meteorológicos por estación")
if not df_tabla.empty:
    df_meteo = df_tabla[["estacion", "ultimo_dia_meteorologico", "ultimos_7_dias_meteorologicos", "ultimos_30_dias_meteorologicos"]].copy()
    df_meteo["estacion"] = df_meteo["estacion"].apply(lambda x: f"sp_{x}")
    df_meteo = df_meteo.round(3)
    df_meteo.columns = ["Estación", "Último día", "Últimos 7 días", "Últimos 30 días"]

    col1, col2 = st.columns([3, 1])
    with col1:
        st.dataframe(df_meteo, use_container_width=True)
    with col2:
        csv_meteo = df_meteo.to_csv(index=False)
        st.download_button(
            label="📥 Descargar CSV",
            data=csv_meteo,
            file_name="acumulados_meteorologicos.csv",
            mime="text/csv"
        )

# Gráfico de acumulados meteorológicos del último día
st.subheader("Acumulado meteorológico del último día por estación")
if not df_tabla.empty:
    df_grafico = df_tabla.copy()
    df_grafico["estacion"] = df_grafico["estacion"].apply(lambda x: f"sp_{x}")

    fig_meteo = px.bar(
        df_grafico,
        x="estacion",
        y="ultimo_dia_meteorologico"
    )
    fig_meteo.update_layout(
        xaxis_title="Estación",
        yaxis_title="Acumulado (mm)",
        showlegend=False,
        xaxis_tickangle=45
    )
    st.plotly_chart(fig_meteo, use_container_width=True)

# Gráfico de estaciones sin datos
st.subheader("Estaciones sin datos por más de 7 días")
if not df_no_reciente.empty:
    df_sin_datos = df_no_reciente.copy()
    df_sin_datos["estacion"] = df_sin_datos["estacion"].apply(lambda x: f"sp_{x}")
    df_sin_datos = df_sin_datos.sort_values("dias_sin_datos", ascending=False)

    fig_sin_datos = px.bar(
        df_sin_datos,
        x="estacion", 
        y="dias_sin_datos"
    )
    fig_sin_datos.update_layout(
        xaxis_title="Estación",
        yaxis_title="Días sin datos",
        xaxis_tickangle=45
    )
    st.plotly_chart(fig_sin_datos, use_container_width=True)
else:
    st.success("🎉 Todas las estaciones tienen datos recientes!")

# Gráfico de disponibilidad de datos
st.subheader("Disponibilidad de datos recientes")
df_pie_chart = df_pie['datos_recientes'].value_counts()
total_estaciones = len(df_pie)

porcentajes = []
labels = []
values = []

for label in df_pie_chart.index:
    count = df_pie_chart[label]
    percentage = (count / total_estaciones) * 100
    porcentajes.append(f"{percentage:.1f}% ({count})")
    labels.append(label)
    values.append(count)

fig_disponibilidad = go.Figure(data=[
    go.Bar(
        x=labels,
        y=[(v/total_estaciones)*100 for v in values],
        text=porcentajes,
        textposition='inside',
        marker_color=['lightcoral' if 'No' in label else 'lightblue' for label in labels]
    )
])

fig_disponibilidad.update_layout(
    xaxis_title="Estado de los datos",
    yaxis_title="Porcentaje (%)",
    yaxis=dict(range=[0, 100]),
    height=400
)

st.plotly_chart(fig_disponibilidad, use_container_width=True)

# Información adicional en el sidebar
st.sidebar.markdown("---")
st.sidebar.markdown("### 📊 Estadísticas generales")
st.sidebar.metric("Total de estaciones", len(df_meta))
st.sidebar.metric("Con datos recientes", len(df_reciente))
st.sidebar.metric("Sin datos recientes", len(df_no_reciente))

# Información sobre actualización
st.sidebar.markdown("---")
st.sidebar.markdown("### ℹ️ Información")
st.sidebar.info("Los datos se actualizan automáticamente cada hora. La aplicación muestra datos de precipitación de las estaciones SAMA.")
