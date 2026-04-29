from flask import Flask, render_template, request, jsonify, redirect, url_for, send_file, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, login_required, logout_user, current_user, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta, date
from collections import defaultdict
from sqlalchemy import func, and_
from apscheduler.schedulers.background import BackgroundScheduler
import pandas as pd
import io
import os
import json
import requests
import smtplib
import random
from email.mime.text import MIMEText

# ─── FORECAST ────────────────────────────────────────────────────────────────
try:
    from statsmodels.tsa.holtwinters import ExponentialSmoothing
    FORECAST_AVAILABLE = True
except ImportError:
    FORECAST_AVAILABLE = False
    print("⚠️ statsmodels no instalado. Forecast deshabilitado. Ejecuta: pip install statsmodels")

app = Flask(__name__)
app.config['SECRET_KEY'] = 'inventa-secret-key-2024-v2'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///inventa.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# ─── CONFIGURACIÓN DE ALERTAS (cambia estos valores) ─────────────────────────
ALERTAS_CONFIG = {
    'telegram_token': os.environ.get('TELEGRAM_BOT_TOKEN', ''),
    'telegram_chat_id': os.environ.get('TELEGRAM_CHAT_ID', ''),
    'smtp_server': 'smtp.gmail.com',
    'smtp_port': 587,
    'smtp_user': os.environ.get('ALERT_EMAIL', ''),
    'smtp_password': os.environ.get('ALERT_EMAIL_PASS', ''),
    'alert_dest_email': os.environ.get('ALERT_DEST_EMAIL', ''),
    'habilitadas': True
}

# ─── MODELOS ACTUALIZADOS ────────────────────────────────────────────────────

class Usuario(db.Model, UserMixin):
    id             = db.Column(db.Integer, primary_key=True)
    nombre         = db.Column(db.String(100), default='Admin')
    email          = db.Column(db.String(100), unique=True)
    password_hash  = db.Column(db.String(200))
    empresa        = db.Column(db.String(100), default='Mi Empresa')
    capital_inicial = db.Column(db.Float, default=0)
    meta_mensual   = db.Column(db.Float, default=0)
    rol            = db.Column(db.String(50), default='admin')
    configuracion  = db.Column(db.Text, default='{}')
    telefono       = db.Column(db.String(50), default='')
    created_at     = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)
    def check_password(self, pw):
        return check_password_hash(self.password_hash, pw)
    
    def get_config(self):
        return json.loads(self.configuracion or '{}')
    
    def set_config(self, config_dict):
        self.configuracion = json.dumps(config_dict)

class Producto(db.Model):
    id           = db.Column(db.Integer, primary_key=True)
    nombre       = db.Column(db.String(200), nullable=False)
    categoria    = db.Column(db.String(100), default='General')
    precio_venta = db.Column(db.Float, default=0)
    costo        = db.Column(db.Float, default=0)
    stock_actual = db.Column(db.Integer, default=0)
    stock_minimo = db.Column(db.Integer, default=10)
    activo       = db.Column(db.Boolean, default=True)
    creado       = db.Column(db.DateTime, default=datetime.utcnow)
    codigo_barras = db.Column(db.String(100), default='')
    ubicacion    = db.Column(db.String(100), default='')

class VentaDetalle(db.Model):
    id              = db.Column(db.Integer, primary_key=True)
    fecha           = db.Column(db.Date, nullable=False)
    producto_nombre = db.Column(db.String(200), nullable=False)
    categoria       = db.Column(db.String(100), default='General')
    cantidad        = db.Column(db.Integer, default=1)
    precio_unitario = db.Column(db.Float, default=0)
    costo_unitario  = db.Column(db.Float, default=0)
    ingreso         = db.Column(db.Float, default=0)
    utilidad        = db.Column(db.Float, default=0)
    subido_en       = db.Column(db.DateTime, default=datetime.utcnow)

class Gasto(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    concepto   = db.Column(db.String(200))
    monto      = db.Column(db.Float)
    tipo       = db.Column(db.String(50), default='fijo')
    frecuencia = db.Column(db.String(50), default='mensual')
    activo     = db.Column(db.Boolean, default=True)

class ResumenVentaDiaria(db.Model):
    id          = db.Column(db.Integer, primary_key=True)
    fecha       = db.Column(db.Date, unique=True, nullable=False)
    total_ingreso = db.Column(db.Float, default=0)
    total_utilidad = db.Column(db.Float, default=0)
    total_cantidad = db.Column(db.Integer, default=0)
    num_transacciones = db.Column(db.Integer, default=0)
    updated_at  = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class AlertaStock(db.Model):
    id           = db.Column(db.Integer, primary_key=True)
    producto_id  = db.Column(db.Integer)
    producto_nombre = db.Column(db.String(200))
    stock_actual = db.Column(db.Integer)
    stock_minimo = db.Column(db.Integer)
    tipo         = db.Column(db.String(50))
    enviado_por  = db.Column(db.String(50))
    fecha_envio  = db.Column(db.DateTime, default=datetime.utcnow)
    leido        = db.Column(db.Boolean, default=False)

# ─── FUNCIONES DE ALERTAS ────────────────────────────────────────────────────

def enviar_alerta_telegram(mensaje):
    if not ALERTAS_CONFIG['habilitadas']:
        return False
    token = ALERTAS_CONFIG['telegram_token']
    chat_id = ALERTAS_CONFIG['telegram_chat_id']
    if not token or not chat_id:
        return False
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {'chat_id': chat_id, 'text': mensaje, 'parse_mode': 'Markdown'}
        r = requests.post(url, json=payload, timeout=5)
        return r.status_code == 200
    except:
        return False

def enviar_alerta_email(asunto, mensaje):
    if not ALERTAS_CONFIG['habilitadas']:
        return False
    smtp_user = ALERTAS_CONFIG['smtp_user']
    smtp_pass = ALERTAS_CONFIG['smtp_password']
    dest = ALERTAS_CONFIG['alert_dest_email']
    if not smtp_user or not dest:
        return False
    try:
        msg = MIMEText(mensaje, 'html', 'utf-8')
        msg['Subject'] = f"[Inventa] {asunto}"
        msg['From'] = smtp_user
        msg['To'] = dest
        with smtplib.SMTP(ALERTAS_CONFIG['smtp_server'], ALERTAS_CONFIG['smtp_port']) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
        return True
    except:
        return False

def verificar_y_enviar_alertas_stock():
    productos = Producto.query.filter_by(activo=True).all()
    alertas_enviadas = []
    
    for p in productos:
        if p.stock_actual <= 0:
            tipo = 'agotado'
            mensaje = f"🚨 *AGOTADO*: {p.nombre} - Stock 0 unidades. ¡Reponer urgentemente!"
        elif p.stock_actual <= p.stock_minimo:
            tipo = 'bajo'
            mensaje = f"⚠️ *Stock Bajo*: {p.nombre} - {p.stock_actual} uds (mínimo {p.stock_minimo})"
        else:
            continue
        
        alerta_reciente = AlertaStock.query.filter(
            and_(AlertaStock.producto_id == p.id, AlertaStock.fecha_envio > datetime.utcnow() - timedelta(hours=24))
        ).first()
        
        if not alerta_reciente:
            ok_telegram = enviar_alerta_telegram(mensaje)
            ok_email = enviar_alerta_email(f"Alerta: {tipo.upper()} - {p.nombre}", mensaje.replace('*', ''))
            
            for canal, ok in [('telegram', ok_telegram), ('email', ok_email)]:
                if ok:
                    db.session.add(AlertaStock(
                        producto_id=p.id, producto_nombre=p.nombre,
                        stock_actual=p.stock_actual, stock_minimo=p.stock_minimo,
                        tipo=tipo, enviado_por=canal
                    ))
            alertas_enviadas.append(p.nombre)
    
    if alertas_enviadas:
        db.session.commit()
        print(f"[OK] Alertas enviadas para: {', '.join(alertas_enviadas)}")
    return alertas_enviadas

def actualizar_resumen_diario(fecha=None):
    if fecha is None:
        fecha = date.today()
    
    ventas_dia = VentaDetalle.query.filter(VentaDetalle.fecha == fecha).all()
    total_ingreso = sum(v.ingreso for v in ventas_dia)
    total_utilidad = sum(v.utilidad for v in ventas_dia)
    total_cantidad = sum(v.cantidad for v in ventas_dia)
    num_tx = len(set(v.id for v in ventas_dia))
    
    resumen = ResumenVentaDiaria.query.filter_by(fecha=fecha).first()
    if resumen:
        resumen.total_ingreso = total_ingreso
        resumen.total_utilidad = total_utilidad
        resumen.total_cantidad = total_cantidad
        resumen.num_transacciones = num_tx
    else:
        db.session.add(ResumenVentaDiaria(
            fecha=fecha, total_ingreso=total_ingreso, total_utilidad=total_utilidad,
            total_cantidad=total_cantidad, num_transacciones=num_tx
        ))
    db.session.commit()

# ─── FORECAST ────────────────────────────────────────────────────────────────

def generar_forecast(dias=30, seasonal_periods=7):
    if not FORECAST_AVAILABLE:
        return {'error': 'statsmodels no instalado', 'forecast': []}
    
    hoy = date.today()
    inicio = hoy - timedelta(days=120)
    
    resumenes = ResumenVentaDiaria.query.filter(
        ResumenVentaDiaria.fecha >= inicio,
        ResumenVentaDiaria.fecha <= hoy
    ).order_by(ResumenVentaDiaria.fecha).all()
    
    if len(resumenes) < 14:
        return {'error': 'Se necesitan al menos 14 días de datos para pronosticar', 'forecast': []}
    
    fechas = [r.fecha for r in resumenes]
    valores = [r.total_ingreso for r in resumenes]
    
    fecha_actual = inicio
    serie_completa = []
    idx = 0
    while fecha_actual <= hoy:
        if idx < len(fechas) and fechas[idx] == fecha_actual:
            serie_completa.append(valores[idx])
            idx += 1
        else:
            serie_completa.append(0)
        fecha_actual += timedelta(days=1)
    
    try:
        model = ExponentialSmoothing(
            serie_completa[-90:],
            seasonal_periods=seasonal_periods,
            trend='add',
            seasonal='add',
            initialization_method='estimated'
        ).fit()
        forecast = model.forecast(dias).tolist()
        
        residuos = model.resid
        mae = sum(abs(r) for r in residuos[-30:]) / len(residuos[-30:]) if len(residuos) >= 30 else 0
        
        return {
            'success': True,
            'forecast': [round(v, 0) for v in forecast],
            'mae': round(mae, 0),
            'confianza': 'Alta' if mae < 100000 else 'Media' if mae < 500000 else 'Baja',
            'dias_analizados': len(serie_completa[-90:])
        }
    except Exception as e:
        return {'error': str(e), 'forecast': []}

# ─── FUNCIONES DE UTILIDAD ───────────────────────────────────────────────────

def fmt_moneda(valor):
    return f"${valor:,.0f}" if valor else "$0"

@login_manager.user_loader
def load_user(uid):
    return Usuario.query.get(int(uid))

# ─── VISTAS ─────────────────────────────────────────────────────────────────

@app.route('/')
def home():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        email    = request.form.get('email','')
        password = request.form.get('password','')
        user = Usuario.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Credenciales incorrectas', 'error')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html')

@app.route('/ventas')
@login_required
def ventas():
    return render_template('ventas.html')

@app.route('/productos')
@login_required
def productos():
    return render_template('productos.html')

@app.route('/proyecciones')
@login_required
def proyecciones():
    return render_template('proyecciones.html')

@app.route('/reportes')
@login_required
def reportes():
    return render_template('reportes.html')

@app.route('/forecast')
@login_required
def forecast_page():
    return render_template('forecast.html')

# ─── API: DASHBOARD ─────────────────────────────────────────────────────────

@app.route('/api/dashboard')
@login_required
def api_dashboard():
    hoy          = date.today()
    ini_semana   = hoy - timedelta(days=hoy.weekday())
    ini_mes      = hoy.replace(day=1)
    mes_anterior = (ini_mes - timedelta(days=1)).replace(day=1)
    
    resumen_hoy = ResumenVentaDiaria.query.filter_by(fecha=hoy).first()
    vhoy = resumen_hoy.total_ingreso if resumen_hoy else 0
    
    resumen_semana = db.session.query(func.sum(ResumenVentaDiaria.total_ingreso)).filter(
        ResumenVentaDiaria.fecha >= ini_semana
    ).scalar() or 0
    
    resumen_mes = db.session.query(func.sum(ResumenVentaDiaria.total_ingreso)).filter(
        ResumenVentaDiaria.fecha >= ini_mes
    ).scalar() or 0
    
    resumen_mes_anterior = db.session.query(func.sum(ResumenVentaDiaria.total_ingreso)).filter(
        ResumenVentaDiaria.fecha.between(mes_anterior, ini_mes - timedelta(days=1))
    ).scalar() or 0
    
    vtotal = db.session.query(func.sum(ResumenVentaDiaria.total_ingreso)).scalar() or 0
    utotal = db.session.query(func.sum(ResumenVentaDiaria.total_utilidad)).scalar() or 0
    margen = round(utotal / vtotal * 100, 1) if vtotal else 0
    alertas = Producto.query.filter(Producto.stock_actual <= Producto.stock_minimo, Producto.activo==True).count()
    
    crecimiento_mes = 0
    if resumen_mes_anterior > 0:
        crecimiento_mes = round((resumen_mes - resumen_mes_anterior) / resumen_mes_anterior * 100, 1)
    
    top = db.session.query(
        VentaDetalle.producto_nombre,
        func.sum(VentaDetalle.cantidad).label('qty'),
        func.sum(VentaDetalle.ingreso).label('ing')
    ).group_by(VentaDetalle.producto_nombre).order_by(func.sum(VentaDetalle.ingreso).desc()).limit(5).all()
    
    ini30 = hoy - timedelta(days=29)
    resumenes = ResumenVentaDiaria.query.filter(
        ResumenVentaDiaria.fecha >= ini30
    ).order_by(ResumenVentaDiaria.fecha).all()
    
    rmap = {r.fecha: r for r in resumenes}
    labels, ingresos, utils = [], [], []
    cur = ini30
    while cur <= hoy:
        labels.append(cur.strftime('%d/%m'))
        r = rmap.get(cur)
        ingresos.append(round(r.total_ingreso, 0) if r else 0)
        utils.append(round(r.total_utilidad, 0) if r else 0)
        cur += timedelta(days=1)
    
    return jsonify({
        'ventas_hoy':        round(vhoy,0),
        'ventas_semana':     round(resumen_semana,0),
        'ventas_mes':        round(resumen_mes,0),
        'ventas_total':      round(vtotal,0),
        'utilidad_total':    round(utotal,0),
        'margen':            margen,
        'alertas_inventario': alertas,
        'total_transacciones': VentaDetalle.query.count(),
        'crecimiento_mensual': crecimiento_mes,
        'top_productos': [{'nombre':p[0],'cantidad':int(p[1]),'ingreso':round(float(p[2]),0)} for p in top],
        'grafica': {'labels':labels,'ingresos':ingresos,'utilidades':utils}
    })

# ─── API: ANÁLISIS COMPARATIVO MoM ───────────────────────────────────────────

@app.route('/api/analisis-comparativo')
@login_required
def api_comparativo():
    hoy = date.today()
    mes_actual = hoy.replace(day=1)
    mes_anterior = (mes_actual - timedelta(days=1)).replace(day=1)
    
    def metrics(start, end):
        q = db.session.query(
            func.sum(VentaDetalle.ingreso).label('ventas'),
            func.sum(VentaDetalle.utilidad).label('utilidad'),
            func.count(VentaDetalle.id).label('tx')
        ).filter(VentaDetalle.fecha.between(start, end)).first()
        return {'ventas': q.ventas or 0, 'utilidad': q.utilidad or 0, 'tx': q.tx or 0}
    
    actual = metrics(mes_actual, hoy)
    anterior = metrics(mes_anterior, mes_actual - timedelta(days=1))
    
    ventas_pct = round((actual['ventas'] - anterior['ventas']) / anterior['ventas'] * 100, 1) if anterior['ventas'] > 0 else 0
    utilidad_pct = round((actual['utilidad'] - anterior['utilidad']) / anterior['utilidad'] * 100, 1) if anterior['utilidad'] > 0 else 0
    
    # Obtener TODOS los productos de ambos meses para emparejar
    productos_actual = db.session.query(
        VentaDetalle.producto_nombre,
        func.sum(VentaDetalle.ingreso).label('ingreso_actual'),
        func.sum(VentaDetalle.cantidad).label('cantidad_actual')
    ).filter(VentaDetalle.fecha >= mes_actual).group_by(VentaDetalle.producto_nombre).all()
    
    productos_anterior = db.session.query(
        VentaDetalle.producto_nombre,
        func.sum(VentaDetalle.ingreso).label('ingreso_anterior'),
        func.sum(VentaDetalle.cantidad).label('cantidad_anterior')
    ).filter(VentaDetalle.fecha.between(mes_anterior, mes_actual - timedelta(days=1))).group_by(VentaDetalle.producto_nombre).all()
    
    # Crear diccionarios para emparejar
    actual_dict = {p[0]: {'ingreso': round(p[1], 0), 'cantidad': int(p[2])} for p in productos_actual}
    anterior_dict = {p[0]: {'ingreso': round(p[1], 0), 'cantidad': int(p[2])} for p in productos_anterior}
    
    # Productos que aparecen en ambos meses (para comparación directa)
    productos_ambos = []
    for prod in actual_dict:
        if prod in anterior_dict:
            ingreso_actual = actual_dict[prod]['ingreso']
            ingreso_anterior = anterior_dict[prod]['ingreso']
            variacion = round((ingreso_actual - ingreso_anterior) / ingreso_anterior * 100, 1) if ingreso_anterior > 0 else 100
            productos_ambos.append({
                'nombre': prod,
                'ingreso_actual': ingreso_actual,
                'ingreso_anterior': ingreso_anterior,
                'variacion': variacion,
                'tendencia': 'positiva' if variacion > 0 else 'negativa',
                'cantidad_actual': actual_dict[prod]['cantidad'],
                'cantidad_anterior': anterior_dict[prod]['cantidad']
            })
    
    # Ordenar por variación (mayor crecimiento primero)
    productos_ambos = sorted(productos_ambos, key=lambda x: x['variacion'], reverse=True)[:10]
    
    # Productos nuevos (solo están en mes actual)
    productos_nuevos = []
    for prod in actual_dict:
        if prod not in anterior_dict:
            productos_nuevos.append({
                'nombre': prod,
                'ingreso': actual_dict[prod]['ingreso'],
                'cantidad': actual_dict[prod]['cantidad']
            })
    productos_nuevos = sorted(productos_nuevos, key=lambda x: x['ingreso'], reverse=True)[:5]
    
    # Productos que desaparecieron
    productos_perdidos = []
    for prod in anterior_dict:
        if prod not in actual_dict:
            productos_perdidos.append({
                'nombre': prod,
                'ingreso': anterior_dict[prod]['ingreso'],
                'cantidad': anterior_dict[prod]['cantidad']
            })
    productos_perdidos = sorted(productos_perdidos, key=lambda x: x['ingreso'], reverse=True)[:5]
    
    return jsonify({
        'mes_actual': {
            'nombre': mes_actual.strftime('%B %Y'),
            'ventas': round(actual['ventas'], 0),
            'utilidad': round(actual['utilidad'], 0),
            'transacciones': actual['tx']
        },
        'mes_anterior': {
            'nombre': mes_anterior.strftime('%B %Y'),
            'ventas': round(anterior['ventas'], 0),
            'utilidad': round(anterior['utilidad'], 0),
            'transacciones': anterior['tx']
        },
        'variacion': {
            'ventas_pct': ventas_pct,
            'utilidad_pct': utilidad_pct,
            'tendencia': 'positiva' if ventas_pct > 0 else 'negativa'
        },
        'productos_comparables': productos_ambos,
        'productos_nuevos': productos_nuevos,
        'productos_perdidos': productos_perdidos
    })

# ─── API: FORECAST ───────────────────────────────────────────────────────────

@app.route('/api/forecast')
@login_required
def api_forecast():
    dias = request.args.get('dias', 30, type=int)
    resultado = generar_forecast(dias=dias)
    
    if resultado.get('success'):
        hoy = date.today()
        fechas_forecast = [(hoy + timedelta(days=i+1)).strftime('%d/%m') for i in range(dias)]
        return jsonify({
            'success': True,
            'fechas': fechas_forecast,
            'forecast': resultado['forecast'],
            'mae': resultado['mae'],
            'confianza': resultado['confianza'],
            'dias_analizados': resultado['dias_analizados']
        })
    else:
        return jsonify({'success': False, 'error': resultado.get('error', 'Error generando forecast')})

# ─── API: CARGA MASIVA DE INVENTARIO ─────────────────────────────────────────

@app.route('/api/upload-inventario', methods=['POST'])
@login_required
def upload_inventario():
    if current_user.rol not in ['admin', 'vendedor']:
        return jsonify({'error': 'No autorizado'}), 403
    
    file = request.files.get('file')
    if not file:
        return jsonify({'error': 'No se recibió archivo'}), 400
    
    try:
        df = pd.read_excel(file)
        df.columns = [c.strip().lower().replace(' ', '_') for c in df.columns]
        
        required = ['nombre', 'precio_venta', 'costo']
        missing = [r for r in required if r not in df.columns]
        if missing:
            return jsonify({'error': f'Faltan columnas: {missing}. Encontradas: {list(df.columns)}'}), 400
        
        nuevos = 0
        actualizados = 0
        errores = []
        
        for idx, row in df.iterrows():
            try:
                nombre = str(row['nombre']).strip()
                if not nombre:
                    errores.append(f"Fila {idx+2}: nombre vacío")
                    continue
                
                precio = float(row['precio_venta'])
                costo = float(row['costo'])
                stock = int(row.get('stock_actual', 0))
                stock_min = int(row.get('stock_minimo', 10))
                categoria = str(row.get('categoria', 'General')).strip()
                codigo = str(row.get('codigo_barras', '')) if 'codigo_barras' in df.columns else ''
                ubicacion = str(row.get('ubicacion', '')) if 'ubicacion' in df.columns else ''
                
                existente = Producto.query.filter_by(nombre=nombre).first()
                if existente:
                    existente.precio_venta = precio
                    existente.costo = costo
                    existente.stock_actual = stock
                    existente.stock_minimo = stock_min
                    existente.categoria = categoria
                    existente.codigo_barras = codigo
                    existente.ubicacion = ubicacion
                    actualizados += 1
                else:
                    db.session.add(Producto(
                        nombre=nombre, categoria=categoria, precio_venta=precio, costo=costo,
                        stock_actual=stock, stock_minimo=stock_min, codigo_barras=codigo, ubicacion=ubicacion
                    ))
                    nuevos += 1
            except Exception as e:
                errores.append(f"Fila {idx+2}: {str(e)}")
        
        db.session.commit()
        
        if nuevos > 0 or actualizados > 0:
            verificar_y_enviar_alertas_stock()
        
        mensaje = f"Carga completada: {nuevos} nuevos, {actualizados} actualizados"
        if errores:
            mensaje += f". Errores: {len(errores)}"
        
        return jsonify({'success': True, 'nuevos': nuevos, 'actualizados': actualizados, 'errores': errores[:10], 'mensaje': mensaje})
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# ─── API: VENTAS ─────────────────────────────────────────────────────────────

@app.route('/api/upload-ventas', methods=['POST'])
@login_required
def upload_ventas():
    file = request.files.get('file')
    if not file:
        return jsonify({'error': 'No se recibió archivo'}), 400
    try:
        df = pd.read_excel(file)
        df.columns = [c.strip().lower().replace(' ', '_') for c in df.columns]

        alias = {
            'fecha':           ['fecha', 'date', 'día', 'dia'],
            'producto':        ['producto', 'product', 'nombre', 'articulo', 'item'],
            'categoria':       ['categoria', 'categoría', 'category'],
            'cantidad':        ['cantidad', 'qty', 'quantity', 'unidades', 'ventas'],
            'precio_unitario': ['precio_unitario', 'precio', 'price', 'pvp', 'valor'],
            'costo_unitario':  ['costo_unitario', 'costo', 'cost', 'costo_unit'],
        }
        m = {}
        for target, opts in alias.items():
            for o in opts:
                if o in df.columns:
                    m[target] = o
                    break

        if 'producto' not in m or 'cantidad' not in m or 'precio_unitario' not in m:
            return jsonify({'error': f'Faltan columnas. Encontradas: {list(df.columns)}. Necesarias: producto, cantidad, precio_unitario'}), 400

        ins = 0
        fechas_afectadas = set()
        
        for _, row in df.iterrows():
            try:
                if 'fecha' in m:
                    fv = row[m['fecha']]
                    fecha = fv.date() if isinstance(fv, (datetime, pd.Timestamp)) else pd.to_datetime(str(fv)).date() if not pd.isna(fv) else date.today()
                else:
                    fecha = date.today()
                
                fechas_afectadas.add(fecha)
                
                prod    = str(row[m['producto']]).strip()
                cant    = int(row[m['cantidad']])
                precio  = float(row[m['precio_unitario']])
                costo   = float(row[m['costo_unitario']]) if ('costo_unitario' in m and not pd.isna(row[m['costo_unitario']])) else precio * 0.6
                cat     = str(row[m['categoria']]).strip() if 'categoria' in m and not pd.isna(row[m['categoria']]) else 'General'

                db.session.add(VentaDetalle(
                    fecha=fecha, producto_nombre=prod, categoria=cat,
                    cantidad=cant, precio_unitario=precio, costo_unitario=costo,
                    ingreso=cant*precio, utilidad=cant*(precio-costo)
                ))
                
                p = Producto.query.filter_by(nombre=prod).first()
                if p:
                    p.stock_actual = max(0, p.stock_actual - cant)
                ins += 1
            except:
                continue

        db.session.commit()
        
        for fecha in fechas_afectadas:
            actualizar_resumen_diario(fecha)
        
        alertas_enviadas = verificar_y_enviar_alertas_stock()
        
        return jsonify({'success': True, 'insertadas': ins, 'alertas_generadas': len(alertas_enviadas)})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# ─── API: PRODUCTOS ──────────────────────────────────────────────────────────

@app.route('/api/productos', methods=['GET'])
@login_required
def api_productos_get():
    ps = Producto.query.filter_by(activo=True).all()
    return jsonify([{
        'id':p.id,'nombre':p.nombre,'categoria':p.categoria,
        'precio_venta':p.precio_venta,'costo':p.costo,
        'stock_actual':p.stock_actual,'stock_minimo':p.stock_minimo,
        'margen':round((p.precio_venta-p.costo)/p.precio_venta*100,1) if p.precio_venta else 0
    } for p in ps])

@app.route('/api/productos', methods=['POST'])
@login_required
def api_productos_add():
    d = request.json
    try:
        p = Producto(nombre=d['nombre'],categoria=d.get('categoria','General'),
            precio_venta=float(d['precio_venta']),costo=float(d['costo']),
            stock_actual=int(d.get('stock_actual',0)),stock_minimo=int(d.get('stock_minimo',10)))
        db.session.add(p); db.session.commit()
        return jsonify({'success':True,'id':p.id})
    except Exception as e:
        db.session.rollback(); return jsonify({'error':str(e)}),400

@app.route('/api/productos/<int:pid>', methods=['PUT'])
@login_required
def api_productos_update(pid):
    p = Producto.query.get_or_404(pid); d = request.json
    p.nombre=d.get('nombre',p.nombre); p.categoria=d.get('categoria',p.categoria)
    p.precio_venta=float(d.get('precio_venta',p.precio_venta)); p.costo=float(d.get('costo',p.costo))
    p.stock_actual=int(d.get('stock_actual',p.stock_actual)); p.stock_minimo=int(d.get('stock_minimo',p.stock_minimo))
    db.session.commit(); return jsonify({'success':True})

@app.route('/api/productos/<int:pid>', methods=['DELETE'])
@login_required
def api_productos_delete(pid):
    p = Producto.query.get_or_404(pid); p.activo=False; db.session.commit()
    return jsonify({'success':True})

# ─── API: INVENTARIO ─────────────────────────────────────────────────────────

@app.route('/api/inventario')
@login_required
def api_inventario():
    ps = Producto.query.filter_by(activo=True).all()
    alertas, sugerencias, promover, resultado = [], [], [], []
    for p in ps:
        margen = (p.precio_venta-p.costo)/p.precio_venta*100 if p.precio_venta else 0
        if p.stock_actual == 0:        estado='agotado'
        elif p.stock_actual <= p.stock_minimo: estado='bajo'
        elif p.stock_actual <= p.stock_minimo*2: estado='medio'
        else:                                  estado='ok'

        if estado in ('agotado','bajo'):
            alertas.append({'producto':p.nombre,'stock_actual':p.stock_actual,'stock_minimo':p.stock_minimo,'estado':estado})
            cant_sug = max(p.stock_minimo*2,20)
            sugerencias.append({'producto':p.nombre,'cantidad_sugerida':cant_sug,'costo_unitario':p.costo,'inversion_estimada':round(cant_sug*p.costo,0)})

        if estado=='ok' and p.stock_actual > p.stock_minimo*3 and margen > 20:
            promover.append({'producto':p.nombre,'stock_actual':p.stock_actual,'margen':round(margen,1),'precio_venta':p.precio_venta})

        resultado.append({'id':p.id,'nombre':p.nombre,'categoria':p.categoria,'precio_venta':p.precio_venta,
            'costo':p.costo,'stock_actual':p.stock_actual,'stock_minimo':p.stock_minimo,'estado':estado,'margen':round(margen,1)})

    return jsonify({'productos':resultado,'alertas':alertas,'sugerencias':sugerencias,'promover':promover,'total_alertas':len(alertas)})

# ─── API: GASTOS ─────────────────────────────────────────────────────────────

@app.route('/api/gastos', methods=['GET'])
@login_required
def api_gastos_get():
    gs = Gasto.query.filter_by(activo=True).all()
    return jsonify({'gastos':[{'id':g.id,'concepto':g.concepto,'monto':g.monto,'tipo':g.tipo,'frecuencia':g.frecuencia} for g in gs],
        'total_fijo':sum(g.monto for g in gs if g.tipo=='fijo'),
        'total_variable':sum(g.monto for g in gs if g.tipo=='variable')})

@app.route('/api/gastos', methods=['POST'])
@login_required
def api_gastos_add():
    d=request.json
    g=Gasto(concepto=d['concepto'],monto=float(d['monto']),tipo=d.get('tipo','fijo'),frecuencia=d.get('frecuencia','mensual'))
    db.session.add(g); db.session.commit(); return jsonify({'success':True,'id':g.id})

@app.route('/api/gastos/<int:gid>', methods=['DELETE'])
@login_required
def api_gastos_delete(gid):
    g=Gasto.query.get_or_404(gid); g.activo=False; db.session.commit(); return jsonify({'success':True})

# ─── API: PROYECCIONES ───────────────────────────────────────────────────────

@app.route('/api/proyeccion/calcular', methods=['POST'])
@login_required
def api_proyeccion():
    d = request.json
    capital    = float(d.get('capital',0))
    gastos_mes = float(d.get('gastos_fijos_mes',0))
    ventas_dia = int(d.get('ventas_diarias_estimadas',10))
    productos  = d.get('productos',[])

    if not productos:
        ps = Producto.query.filter_by(activo=True).all()
        productos = [{'precio':p.precio_venta,'costo':p.costo,'cantidad_dia':1} for p in ps]
    if not productos:
        return jsonify({'error':'No hay productos configurados'}),400

    tp   = sum(p.get('precio',0)*p.get('cantidad_dia',1) for p in productos)
    tc   = sum(p.get('costo',0)*p.get('cantidad_dia',1) for p in productos)
    tqty = sum(p.get('cantidad_dia',1) for p in productos)

    if tp==0: return jsonify({'error':'Precio no puede ser 0'}),400
    pprom = tp/tqty; cprom = tc/tqty; margen_u = pprom-cprom
    if margen_u<=0: return jsonify({'error':'El precio debe ser mayor al costo'}),400

    gdia        = gastos_mes/30
    uq_eq_dia   = gdia/margen_u
    vq_eq_dia   = uq_eq_dia*pprom
    ing_dia     = ventas_dia*pprom
    util_dia    = ventas_dia*margen_u - gdia
    dias_rec    = round(capital/util_dia,0) if util_dia>0 else -1

    proyecciones = []
    acum = -capital
    mes_utilidad = None
    for mes in range(1,13):
        util_mes = util_dia*30
        acum += util_mes
        proyecciones.append({'mes':mes,'ingreso':round(ing_dia*30,0),'costos':round((cprom*ventas_dia+gdia)*30,0),'utilidad':round(util_mes,0),'capital_acumulado':round(acum,0)})
        if mes_utilidad is None and acum>=0:
            mes_utilidad=mes

    return jsonify({
        'precio_promedio':round(pprom,0),'costo_promedio':round(cprom,0),
        'margen_contribucion':round(margen_u,0),'margen_porcentaje':round(margen_u/pprom*100,1),
        'gastos_fijos_dia':round(gdia,0),'unidades_equilibrio_dia':round(uq_eq_dia,1),
        'ventas_equilibrio_dia':round(vq_eq_dia,0),'ingreso_diario_estimado':round(ing_dia,0),
        'utilidad_diaria_estimada':round(util_dia,0),'dias_recuperacion_capital':dias_rec,
        'mes_inicio_utilidades':mes_utilidad,'proyecciones_mensuales':proyecciones
    })

# ─── API: REPORTES ───────────────────────────────────────────────────────────

@app.route('/api/reporte/excel')
@login_required
def api_reporte_excel():
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    hdr_font  = Font(bold=True,color='FFFFFF',size=11)
    hdr_fill  = PatternFill(start_color='0071E3',end_color='0071E3',fill_type='solid')
    hdr_fill2 = PatternFill(start_color='1D1D1F',end_color='1D1D1F',fill_type='solid')

    def set_headers(ws, headers, fill):
        for c,h in enumerate(headers,1):
            cell=ws.cell(row=1,column=c,value=h)
            cell.font=hdr_font; cell.fill=fill; cell.alignment=Alignment(horizontal='center')
        for c in range(1,len(headers)+1):
            ws.column_dimensions[get_column_letter(c)].width=16

    ws1=wb.active; ws1.title='Ventas'
    set_headers(ws1,['Fecha','Producto','Categoria','Cantidad','Precio','Costo','Ingreso','Utilidad'],hdr_fill)
    for i,v in enumerate(VentaDetalle.query.order_by(VentaDetalle.fecha.desc()).all(),2):
        ws1.append([v.fecha.strftime('%Y-%m-%d') if v.fecha else '',v.producto_nombre,v.categoria,v.cantidad,v.precio_unitario,v.costo_unitario,v.ingreso,v.utilidad])

    ws2=wb.create_sheet('Analisis')
    set_headers(ws2,['Producto','Categoria','Cant. Vendida','Ingresos','Utilidad','Margen %'],hdr_fill2)
    rows=db.session.query(VentaDetalle.producto_nombre,VentaDetalle.categoria,func.sum(VentaDetalle.cantidad),func.sum(VentaDetalle.ingreso),func.sum(VentaDetalle.utilidad)).group_by(VentaDetalle.producto_nombre,VentaDetalle.categoria).order_by(func.sum(VentaDetalle.ingreso).desc()).all()
    for i,r in enumerate(rows,2):
        ing=float(r[3]); util=float(r[4])
        ws2.append([r[0],r[1],int(r[2]),round(ing,0),round(util,0),round(util/ing*100,1) if ing>0 else 0])

    ws3=wb.create_sheet('Inventario')
    set_headers(ws3,['Producto','Categoria','Stock','Stock Min.','Precio','Costo','Estado'],hdr_fill)
    for p in Producto.query.filter_by(activo=True).all():
        estado='AGOTADO' if p.stock_actual==0 else 'BAJO' if p.stock_actual<=p.stock_minimo else 'OK'
        ws3.append([p.nombre,p.categoria,p.stock_actual,p.stock_minimo,p.precio_venta,p.costo,estado])

    out=io.BytesIO(); wb.save(out); out.seek(0)
    return send_file(out,mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,download_name=f'reporte_inventa_{date.today().strftime("%Y%m%d")}.xlsx')

@app.route('/api/reporte/pdf')
@login_required
def api_reporte_pdf():
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.units import cm
    from reportlab.lib.enums import TA_CENTER

    buf=io.BytesIO()
    doc=SimpleDocTemplate(buf,pagesize=A4,leftMargin=2*cm,rightMargin=2*cm,topMargin=2*cm,bottomMargin=2*cm)
    styles=getSampleStyleSheet()
    BLUE=colors.HexColor('#0071E3'); DARK=colors.HexColor('#1d1d1f'); LIGHT=colors.HexColor('#f5f5f7')

    t_style=ParagraphStyle('t',parent=styles['Heading1'],fontSize=22,textColor=BLUE,spaceAfter=4,alignment=TA_CENTER)
    h2=ParagraphStyle('h2',parent=styles['Heading2'],fontSize=13,textColor=DARK,spaceAfter=6)

    vtotal=db.session.query(func.sum(VentaDetalle.ingreso)).scalar() or 0
    utotal=db.session.query(func.sum(VentaDetalle.utilidad)).scalar() or 0
    margen=round(utotal/vtotal*100,1) if vtotal else 0

    story=[
        Paragraph('INVENTA — Reporte Empresarial',t_style),
        Paragraph(f'Generado: {datetime.now().strftime("%d/%m/%Y %H:%M")} | {current_user.empresa}',styles['Normal']),
        Spacer(1,0.4*cm),
        Paragraph('Resumen Ejecutivo',h2),
    ]

    kpi_t=Table([['Metrica','Valor'],['Ventas Totales',f'${vtotal:,.0f}'],['Utilidad Total',f'${utotal:,.0f}'],['Margen Prom.',f'{margen}%'],['Transacciones',str(VentaDetalle.query.count())]],colWidths=[8*cm,8*cm])
    kpi_t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),BLUE),('TEXTCOLOR',(0,0),(-1,0),colors.white),('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTSIZE',(0,0),(-1,-1),11),('ROWBACKGROUNDS',(0,1),(-1,-1),[LIGHT,colors.white]),('GRID',(0,0),(-1,-1),0.5,colors.HexColor('#d2d2d7')),('PADDING',(0,0),(-1,-1),8)]))
    story+=[kpi_t,Spacer(1,0.4*cm),Paragraph('Top Productos',h2)]

    tops=db.session.query(VentaDetalle.producto_nombre,func.sum(VentaDetalle.cantidad),func.sum(VentaDetalle.ingreso),func.sum(VentaDetalle.utilidad)).group_by(VentaDetalle.producto_nombre).order_by(func.sum(VentaDetalle.ingreso).desc()).limit(10).all()
    if tops:
        pd_data=[['Producto','Cant.','Ingresos','Utilidad']]+[[r[0],str(int(r[1])),f'${float(r[2]):,.0f}',f'${float(r[3]):,.0f}'] for r in tops]
        pt=Table(pd_data,colWidths=[7*cm,3*cm,4*cm,3.5*cm])
        pt.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),DARK),('TEXTCOLOR',(0,0),(-1,0),colors.white),('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTSIZE',(0,0),(-1,-1),10),('ROWBACKGROUNDS',(0,1),(-1,-1),[LIGHT,colors.white]),('GRID',(0,0),(-1,-1),0.5,colors.HexColor('#d2d2d7')),('PADDING',(0,0),(-1,-1),6)]))
        story.append(pt)

    story+=[Spacer(1,0.4*cm),Paragraph('Alertas de Inventario',h2)]
    alertas=Producto.query.filter(Producto.stock_actual<=Producto.stock_minimo,Producto.activo==True).all()
    if alertas:
        ad=[['Producto','Stock','Minimo','Estado']]+[[p.nombre,str(p.stock_actual),str(p.stock_minimo),'AGOTADO' if p.stock_actual==0 else 'BAJO'] for p in alertas]
        at=Table(ad,colWidths=[7*cm,3*cm,3*cm,3*cm])
        at.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#FF453A')),('TEXTCOLOR',(0,0),(-1,0),colors.white),('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTSIZE',(0,0),(-1,-1),10),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.HexColor('#fff5f4'),colors.white]),('GRID',(0,0),(-1,-1),0.5,colors.HexColor('#d2d2d7')),('PADDING',(0,0),(-1,-1),6)]))
        story.append(at)
    else:
        story.append(Paragraph('No hay alertas de inventario activas.',styles['Normal']))

    doc.build(story); buf.seek(0)
    return send_file(buf,mimetype='application/pdf',as_attachment=True,download_name=f'reporte_inventa_{date.today().strftime("%Y%m%d")}.pdf')

# ─── API: ALERTAS ────────────────────────────────────────────────────────────

@app.route('/api/alertas')
@login_required
def api_alertas_lista():
    alertas = AlertaStock.query.order_by(AlertaStock.fecha_envio.desc()).limit(50).all()
    return jsonify([{
        'id': a.id,
        'producto': a.producto_nombre,
        'stock_actual': a.stock_actual,
        'stock_minimo': a.stock_minimo,
        'tipo': a.tipo,
        'fecha': a.fecha_envio.strftime('%Y-%m-%d %H:%M'),
        'leido': a.leido
    } for a in alertas])

@app.route('/api/alertas/marcar-leida/<int:alerta_id>', methods=['POST'])
@login_required
def api_alerta_marcar_leida(alerta_id):
    alerta = AlertaStock.query.get_or_404(alerta_id)
    alerta.leido = True
    db.session.commit()
    return jsonify({'success': True})

# ─── API: ANALISIS INTELIGENTE ───────────────────────────────────────────────

@app.route('/api/analisis-inteligente')
@login_required
def api_analisis_inteligente():
    hoy   = date.today()
    ini60 = hoy - timedelta(days=60)
    dias_datos = 60

    ventas_rows = db.session.query(
        VentaDetalle.producto_nombre,
        func.sum(VentaDetalle.cantidad).label('total_qty'),
        func.sum(VentaDetalle.ingreso).label('total_ing'),
        func.sum(VentaDetalle.utilidad).label('total_util'),
        func.count(VentaDetalle.id).label('num_tx'),
        func.min(VentaDetalle.fecha).label('primera_venta'),
        func.max(VentaDetalle.fecha).label('ultima_venta'),
    ).filter(VentaDetalle.fecha >= ini60).group_by(VentaDetalle.producto_nombre).all()

    ventas_dict = {}
    for r in ventas_rows:
        ventas_dict[r[0]] = {
            'total_qty':   int(r[1]),
            'total_ing':   round(float(r[2]),0),
            'total_util':  round(float(r[3]),0),
            'num_tx':      int(r[4]),
            'velocidad':   round(int(r[1])/dias_datos, 2),
        }

    productos = Producto.query.filter_by(activo=True).all()
    hay_ventas = bool(ventas_dict)

    sacar       = []
    promover    = []
    mantener    = []
    sin_ventas  = []

    for p in productos:
        margen_pct = (p.precio_venta - p.costo) / p.precio_venta * 100 if p.precio_venta else 0
        v = ventas_dict.get(p.nombre)

        if not hay_ventas:
            if p.stock_actual > p.stock_minimo * 5:
                sin_ventas.append({'nombre': p.nombre, 'categoria': p.categoria, 'stock_actual': p.stock_actual, 'precio_venta': p.precio_venta, 'costo': p.costo, 'margen': round(margen_pct,1)})
            continue

        if not v:
            sin_ventas.append({
                'nombre': p.nombre, 'categoria': p.categoria,
                'stock_actual': p.stock_actual, 'precio_venta': p.precio_venta,
                'costo': p.costo, 'margen': round(margen_pct,1),
                'razon': 'Sin ventas en 60 dias'
            })
            continue

        velocidad   = v['velocidad']
        dias_stock  = p.stock_actual / velocidad if velocidad > 0 else 9999
        descuento_sug  = min(30, max(10, int((dias_stock - 30) / 10) * 5)) if dias_stock > 30 else 10
        precio_promo   = round(max(p.costo * 1.05, p.precio_venta * (1 - descuento_sug/100)), -3)

        item = {
            'nombre': p.nombre, 'categoria': p.categoria,
            'stock_actual': p.stock_actual, 'precio_venta': p.precio_venta, 'costo': p.costo,
            'margen': round(margen_pct,1), 'velocidad': velocidad, 'dias_stock_restante': round(dias_stock,0),
            'precio_promo': precio_promo, 'descuento_pct': descuento_sug
        }

        if dias_stock > 90 and margen_pct < 15:
            item['razon'] = f'Exceso de stock ({int(dias_stock)} dias) y margen bajo ({round(margen_pct,1)}%)'
            sacar.append(item)
        elif dias_stock > 45 and velocidad < 0.5:
            item['razon'] = f'Rotacion lenta ({velocidad}/dia)'
            promover.append(item)
        elif margen_pct > 30 and velocidad < 1.0 and p.stock_actual > p.stock_minimo * 2:
            item['razon'] = f'Buen margen pero rotacion lenta'
            promover.append(item)
        else:
            mantener.append(item)

    total_ventas   = sum(v['total_ing'] for v in ventas_dict.values())
    total_util_60  = sum(v['total_util'] for v in ventas_dict.values())

    return jsonify({
        'sacar': sacar,
        'promover': promover,
        'mantener': mantener,
        'sin_ventas': sin_ventas,
        'resumen': {
            'total_productos': len(productos),
            'productos_con_ventas': len([p for p in productos if p.nombre in ventas_dict]),
            'ventas_60_dias': round(total_ventas, 0),
            'utilidad_60_dias': round(total_util_60, 0),
            'criticos': len(sacar) + len(sin_ventas),
            'oportunidades': len(promover),
        }
    })

# ─── API: DEMO DATA ──────────────────────────────────────────────────────────

@app.route('/api/demo-data', methods=['POST'])
@login_required
def api_demo_data():
    from sqlalchemy import delete
    
    random.seed(42)
    
    db.session.execute(delete(VentaDetalle))
    db.session.execute(delete(Producto))
    db.session.execute(delete(Gasto))
    db.session.execute(delete(ResumenVentaDiaria))
    db.session.commit()
    
    demo_prods = [
        ('Camiseta Basica', 'Ropa', 45000, 20000, 150, 20),
        ('Jeans Premium', 'Ropa', 120000, 60000, 80, 15),
        ('Zapatillas Sport', 'Calzado', 180000, 90000, 60, 10),
        ('Mochila Urbana', 'Accesorios', 95000, 45000, 45, 8),
        ('Audifonos BT', 'Electronica', 85000, 40000, 30, 5),
        ('Reloj Casual', 'Accesorios', 65000, 30000, 25, 5),
        ('Sudadera Hoodie', 'Ropa', 89000, 42000, 90, 15),
        ('Gorra Snapback', 'Accesorios', 35000, 15000, 120, 10),
        ('Lentes de Sol', 'Accesorios', 55000, 25000, 40, 8),
        ('Botas Tacticas', 'Calzado', 220000, 120000, 20, 5),
    ]
    
    productos_obj = []
    for n, c, pv, co, sa, sm in demo_prods:
        productos_obj.append(Producto(
            nombre=n, categoria=c, precio_venta=pv, costo=co,
            stock_actual=sa, stock_minimo=sm
        ))
    db.session.add_all(productos_obj)
    db.session.commit()
    
    gastos_obj = [
        Gasto(concepto='Arriendo', monto=1500000, tipo='fijo', frecuencia='mensual'),
        Gasto(concepto='Servicios', monto=250000, tipo='fijo', frecuencia='mensual'),
        Gasto(concepto='Nomina', monto=2500000, tipo='fijo', frecuencia='mensual'),
        Gasto(concepto='Marketing', monto=300000, tipo='variable', frecuencia='mensual'),
        Gasto(concepto='Transporte', monto=150000, tipo='variable', frecuencia='mensual'),
    ]
    db.session.add_all(gastos_obj)
    db.session.commit()
    
    hoy = date.today()
    productos_lista = [(p.nombre, p.categoria, p.precio_venta, p.costo) for p in productos_obj]
    ventas_para_insertar = []
    
    for d in range(60, -1, -1):
        fecha = hoy - timedelta(days=d)
        num_ventas = random.randint(5, 15)
        
        for _ in range(num_ventas):
            prod = random.choice(productos_lista)
            cant = random.randint(1, 8)
            precio = round(prod[2] * random.uniform(0.92, 1.08), -2)
            ingreso = cant * precio
            utilidad = cant * (precio - prod[3])
            
            ventas_para_insertar.append(VentaDetalle(
                fecha=fecha, producto_nombre=prod[0], categoria=prod[1],
                cantidad=cant, precio_unitario=precio, costo_unitario=prod[3],
                ingreso=ingreso, utilidad=utilidad
            ))
    
    db.session.bulk_save_objects(ventas_para_insertar)
    db.session.commit()
    
    # Actualizar resumenes diarios
    for d in range(60, -1, -1):
        actualizar_resumen_diario(hoy - timedelta(days=d))
    
    # Actualizar stock
    ventas_por_producto = db.session.query(
        VentaDetalle.producto_nombre,
        func.sum(VentaDetalle.cantidad).label('total_vendido')
    ).group_by(VentaDetalle.producto_nombre).all()
    
    for prod_nombre, total_vendido in ventas_por_producto:
        prod = Producto.query.filter_by(nombre=prod_nombre).first()
        if prod:
            prod.stock_actual = max(0, prod.stock_actual - total_vendido)
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'mensaje': f'Datos demo cargados: {len(productos_obj)} productos, {len(ventas_para_insertar)} ventas'
    })

# ─── API: LIMPIAR DATOS ──────────────────────────────────────────────────────

@app.route('/api/datos', methods=['DELETE'])
@login_required
def api_limpiar_datos():
    tipo = request.args.get('tipo', 'ventas')
    try:
        if tipo == 'ventas':
            VentaDetalle.query.delete()
            ResumenVentaDiaria.query.delete()
        elif tipo == 'todo':
            VentaDetalle.query.delete()
            Producto.query.delete()
            Gasto.query.delete()
            ResumenVentaDiaria.query.delete()
        db.session.commit()
        msg = 'Todos los datos eliminados' if tipo=='todo' else 'Historial de ventas eliminado'
        return jsonify({'success': True, 'mensaje': msg})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# ─── API: CONFIGURACION DE USUARIO ───────────────────────────────────────────

@app.route('/api/config', methods=['GET', 'POST'])
@login_required
def api_config():
    u = current_user
    if request.method == 'POST':
        d = request.json
        u.empresa = d.get('empresa', u.empresa)
        u.capital_inicial = float(d.get('capital_inicial', u.capital_inicial))
        u.meta_mensual = float(d.get('meta_mensual', u.meta_mensual))
        u.rol = d.get('rol', u.rol)
        u.telefono = d.get('telefono', u.telefono)
        if 'configuracion' in d:
            u.set_config(d['configuracion'])
        db.session.commit()
        
        if 'alertas_config' in d:
            global ALERTAS_CONFIG
            ALERTAS_CONFIG.update(d['alertas_config'])
        
        return jsonify({'success': True})
    return jsonify({
        'empresa': u.empresa, 'capital_inicial': u.capital_inicial, 'meta_mensual': u.meta_mensual,
        'rol': u.rol, 'telefono': u.telefono, 'configuracion': u.get_config()
    })

# ─── API: VENTAS ANALISIS ────────────────────────────────────────────────────

@app.route('/api/ventas/analisis')
@login_required
def api_ventas_analisis():
    periodo = request.args.get('periodo','mes')
    hoy = date.today()
    inicio = {'dia':hoy,'semana':hoy-timedelta(days=hoy.weekday()),'mes':hoy.replace(day=1),'todo':date(2000,1,1)}.get(periodo, hoy.replace(day=1))

    rows = db.session.query(
        VentaDetalle.producto_nombre, VentaDetalle.categoria,
        func.sum(VentaDetalle.cantidad), func.sum(VentaDetalle.ingreso), func.sum(VentaDetalle.utilidad)
    ).filter(VentaDetalle.fecha >= inicio).group_by(VentaDetalle.producto_nombre, VentaDetalle.categoria).all()

    lista = [{'nombre':r[0],'categoria':r[1],'cantidad':int(r[2]),'ingreso':round(float(r[3]),0),'utilidad':round(float(r[4]),0),'margen':round(float(r[4])/float(r[3])*100,1) if float(r[3])>0 else 0} for r in rows]
    by_ing = sorted(lista, key=lambda x: x['ingreso'], reverse=True)

    cat = defaultdict(float)
    for p in lista: cat[p['categoria']] += p['ingreso']

    return jsonify({
        'productos': by_ing,
        'estrella': by_ing[0] if by_ing else None,
        'peor': by_ing[-1] if len(by_ing)>1 else None,
        'top5': by_ing[:5],
        'categorias': [{'nombre':k,'ingreso':round(v,0)} for k,v in sorted(cat.items(),key=lambda x:-x[1])]
    })

# ─── INIT Y SCHEDULER ────────────────────────────────────────────────────────

# ─── INIT Y SCHEDULER ────────────────────────────────────────────────────────

def init_db():
    """Inicializa la base de datos y crea usuarios por defecto si no existen"""
    with app.app_context():
        db.create_all()
        if not Usuario.query.first():
            # Usuario ADMIN
            admin = Usuario(
                nombre='Admin', 
                email='admin@inventa.com', 
                empresa='Mi Empresa', 
                rol='admin'
            )
            admin.set_password('inventa2024')
            db.session.add(admin)
            
            # Usuario VENDEDOR (demo)
            vendedor = Usuario(
                nombre='Vendedor Demo', 
                email='vendedor@inventa.com', 
                empresa='Mi Empresa', 
                rol='vendedor'
            )
            vendedor.set_password('demo123')
            db.session.add(vendedor)
            
            # Usuario CONSULTOR (demo)
            consultor = Usuario(
                nombre='Consultor Demo', 
                email='consultor@inventa.com', 
                empresa='Mi Empresa', 
                rol='consultor'
            )
            consultor.set_password('ver123')
            db.session.add(consultor)
            
            db.session.commit()
            print('[OK] Credenciales creadas:')
            print('   admin@inventa.com / inventa2024 (Administrador)')
            print('   vendedor@inventa.com / demo123 (Vendedor)')
            print('   consultor@inventa.com / ver123 (Consultor)')


# ─── CONFIGURACIÓN PARA PRODUCCIÓN VS LOCAL ───────────────────────────────────

# Detectar si estamos en producción (Render, PythonAnywhere, etc.)
# Render setea la variable de entorno PORT automáticamente
ENV_PRODUCCION = os.environ.get('PORT') is not None

if ENV_PRODUCCION:
    print("[INFO] Ejecutando en MODO PRODUCCIÓN")
    # En producción: solo inicializar BD, NO scheduler
    with app.app_context():
        init_db()
else:
    print("[INFO] Ejecutando en MODO LOCAL")
    # En local: inicializar BD y scheduler
    with app.app_context():
        init_db()
    
    # Iniciar scheduler SOLO en desarrollo local
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        func=lambda: verificar_y_enviar_alertas_stock(), 
        trigger="interval", 
        hours=6, 
        id="alertas_stock"
    )
    scheduler.add_job(
        func=lambda: actualizar_resumen_diario(date.today()), 
        trigger="interval", 
        hours=24, 
        id="resumen_diario"
    )
    scheduler.start()
    print("[OK] Scheduler de alertas activado (solo local)")


# ─── PUNTO DE ENTRADA ────────────────────────────────────────────────────────

if __name__ == '__main__':
    # Esto se ejecuta SOLO cuando corres "python app.py" en tu PC
    app.run(debug=True, host='0.0.0.0', port=5000)