// ─── UTILIDADES GLOBALES ───────────────────────────────────────────────────

/** Formatea número como pesos colombianos: $1.234.567 */
function fmt(n) {
  if (n === null || n === undefined || isNaN(n)) return '$0';
  const v = Math.round(Number(n));
  return (v < 0 ? '-$' : '$') + Math.abs(v).toLocaleString('es-CO', { maximumFractionDigits: 0 });
}

/** Versión corta para gráficas: $1,2 M · $350 mil */
function fmtCorto(n) {
  const v = Math.abs(Number(n) || 0), s = n < 0 ? '-' : '';
  if (v >= 1e6) return `${s}$${(v / 1e6).toLocaleString('es-CO', { maximumFractionDigits: 1 })} M`;
  if (v >= 1e3) return `${s}$${Math.round(v / 1e3).toLocaleString('es-CO')} mil`;
  return fmt(n);
}

/** Porcentaje con signo; null → "—" */
function pct(v, signo = true) {
  if (v === null || v === undefined || isNaN(v)) return '—';
  return `${signo && v > 0 ? '+' : ''}${Number(v).toLocaleString('es-CO', { maximumFractionDigits: 1 })}%`;
}

/** Escapa texto antes de insertarlo con innerHTML (evita inyección de código) */
function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function fechaLocalISO(d = new Date()) {
  const z = n => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${z(d.getMonth() + 1)}-${z(d.getDate())}`;
}

function fechaCorta(iso) {
  if (!iso) return '';
  const [y, m, d] = iso.split('-');
  return `${d}/${m}/${y}`;
}

const PUEDE_EDITAR = document.body.dataset.puedeEditar === '1';
const ES_ADMIN = document.body.dataset.esAdmin === '1';

/**
 * Llamada a la API: añade el encabezado anti-CSRF, convierte JSON y
 * lanza un Error con el mensaje del servidor si algo falla.
 */
async function api(url, opts = {}) {
  const o = { ...opts, headers: { 'X-Requested-With': 'fetch', ...(opts.headers || {}) } };
  if (o.body && !(o.body instanceof FormData) && typeof o.body !== 'string') {
    o.body = JSON.stringify(o.body);
    o.headers['Content-Type'] = 'application/json';
  }
  let r;
  try {
    r = await fetch(url, o);
  } catch (e) {
    throw new Error('Sin conexión con el servidor. Revisa tu internet.');
  }
  if (r.status === 401) {
    location.href = '/login?next=' + encodeURIComponent(location.pathname);
    throw new Error('Sesión expirada');
  }
  const tipo = r.headers.get('content-type') || '';
  if (!tipo.includes('application/json')) {
    if (!r.ok) throw new Error(`Error del servidor (${r.status})`);
    return r;
  }
  const d = await r.json();
  if (!r.ok || d.success === false) throw new Error(d.error || `Error (${r.status})`);
  return d;
}

/** Descarga un archivo de la API respetando la sesión */
async function descargar(url, nombre) {
  const r = await api(url);
  const blob = await r.blob();
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  const cd = r.headers.get('content-disposition') || '';
  const m = cd.match(/filename="?([^"]+)"?/);
  a.download = m ? m[1] : nombre;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

/** Notificación flotante */
function toast(msg, type = 'info', duration = 3800) {
  const container = document.getElementById('toast-container');
  if (!container) return;
  const icons = { success: '✓', error: '!', info: 'i', warning: '!' };
  const t = document.createElement('div');
  t.className = `toast ${type}`;
  t.innerHTML = `<span class="toast-icon">${icons[type] || 'i'}</span><span>${esc(msg)}</span>`;
  container.appendChild(t);
  setTimeout(() => {
    t.classList.add('saliendo');
    setTimeout(() => t.remove(), 300);
  }, duration);
}

/** Botón en estado de carga mientras corre una promesa */
async function conCarga(btn, fn, texto = 'Procesando...') {
  const orig = btn ? btn.innerHTML : null;
  if (btn) { btn.disabled = true; btn.innerHTML = `<span class="spinner"></span> ${texto}`; }
  try { return await fn(); }
  finally { if (btn) { btn.disabled = false; btn.innerHTML = orig; } }
}

// ─── MODALES ───────────────────────────────────────────────────────────────

function openModal(id) {
  const el = document.getElementById(id);
  if (!el) return;
  el.classList.add('open');
  document.body.classList.add('modal-abierto');
  setTimeout(() => el.querySelector('input:not([type=hidden]),select,textarea')?.focus(), 80);
}

function closeModal(id) {
  const el = document.getElementById(id);
  if (el) el.classList.remove('open');
  if (!document.querySelector('.modal-overlay.open')) document.body.classList.remove('modal-abierto');
}

function cerrarOverlay(id) {
  // La confirmación debe responder "no" al cerrarse, para no dejar la acción colgada
  if (id === 'modal-confirmar') document.getElementById('mc-cancelar').click();
  else closeModal(id);
}

document.addEventListener('click', (e) => {
  if (e.target.classList.contains('modal-overlay')) cerrarOverlay(e.target.id);
});

document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    document.querySelectorAll('.modal-overlay.open').forEach(m => cerrarOverlay(m.id));
    toggleSidebar(false);
  }
});

/** Confirmación con estilo propio. Devuelve una promesa con true/false. */
function confirmar(texto, { titulo = '¿Confirmas?', boton = 'Confirmar', peligro = true } = {}) {
  return new Promise(resolve => {
    document.getElementById('mc-titulo').textContent = titulo;
    document.getElementById('mc-texto').textContent = texto;
    const ok = document.getElementById('mc-aceptar');
    const no = document.getElementById('mc-cancelar');
    ok.textContent = boton;
    ok.className = `btn ${peligro ? 'btn-danger' : 'btn-primary'}`;
    const cerrar = (v) => { closeModal('modal-confirmar'); ok.onclick = no.onclick = null; resolve(v); };
    ok.onclick = () => cerrar(true);
    no.onclick = () => cerrar(false);
    openModal('modal-confirmar');
  });
}

// ─── NAVEGACIÓN ────────────────────────────────────────────────────────────

function toggleSidebar(forzar) {
  const s = document.getElementById('sidebar');
  if (!s) return;
  const abrir = forzar === undefined ? !s.classList.contains('open') : forzar;
  s.classList.toggle('open', abrir);
  document.getElementById('sidebar-backdrop')?.classList.toggle('open', abrir);
}

document.querySelectorAll('.nav-item, .bn-item').forEach(el => {
  if (el.getAttribute('href') === location.pathname) el.classList.add('active');
});

const fechaEl = document.getElementById('current-date');
if (fechaEl) {
  fechaEl.textContent = new Date().toLocaleDateString('es-CO', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });
}

// ─── CHART.JS ──────────────────────────────────────────────────────────────

if (typeof Chart !== 'undefined') {
  Chart.defaults.font.family = "'DM Sans', -apple-system, sans-serif";
  Chart.defaults.color = '#8b98ab';
  Chart.defaults.borderColor = 'rgba(255,255,255,0.05)';
  Chart.defaults.plugins.tooltip.padding = 10;
  Chart.defaults.plugins.tooltip.cornerRadius = 8;
  Chart.defaults.plugins.tooltip.backgroundColor = '#0f1620';
  Chart.defaults.plugins.tooltip.borderColor = 'rgba(255,255,255,0.12)';
  Chart.defaults.plugins.tooltip.borderWidth = 1;
  Chart.defaults.plugins.legend.labels.usePointStyle = true;
  Chart.defaults.plugins.legend.labels.pointStyleWidth = 8;
  Chart.defaults.animation.duration = 600;
  Chart.defaults.maintainAspectRatio = false;
}

// ─── ZONAS DE ARRASTRE ─────────────────────────────────────────────────────

/** Conecta una zona de carga a una función que recibe el archivo */
function conectarZonaCarga(zona, alSoltar) {
  if (!zona) return;
  const input = zona.querySelector('input[type=file]');
  zona.addEventListener('dragover', e => { e.preventDefault(); zona.classList.add('drag-over'); });
  zona.addEventListener('dragleave', () => zona.classList.remove('drag-over'));
  zona.addEventListener('drop', e => {
    e.preventDefault();
    zona.classList.remove('drag-over');
    const f = e.dataTransfer.files[0];
    if (f) alSoltar(f);
  });
  input?.addEventListener('change', e => {
    const f = e.target.files[0];
    if (f) alSoltar(f);
    e.target.value = '';
  });
}

// ─── REGISTRAR VENTA (disponible en todas las páginas) ─────────────────────

let catalogoVenta = [];

async function abrirVenta(productoId) {
  if (!document.getElementById('modal-venta')) return;
  try {
    catalogoVenta = await api('/api/productos');
  } catch (e) {
    toast(e.message, 'error');
    return;
  }
  document.getElementById('mv-fecha').value = fechaLocalISO();
  document.getElementById('mv-fecha').max = fechaLocalISO();
  document.getElementById('mv-lineas').innerHTML = '';
  agregarLinea(productoId);
  openModal('modal-venta');
}

function agregarLinea(productoId) {
  const cont = document.getElementById('mv-lineas');
  const div = document.createElement('div');
  div.className = 'venta-linea';
  const opciones = catalogoVenta.map(p =>
    `<option value="${p.id}">${esc(p.nombre)} — ${fmt(p.precio_venta)}</option>`).join('');
  div.innerHTML = `
    <div class="vl-producto">
      <label class="form-label">Producto</label>
      <select class="form-control vl-select">
        ${catalogoVenta.length ? '<option value="">Elige un producto…</option>' : ''}
        ${opciones}
        <option value="otro">✎ Otro (no está en el catálogo)</option>
      </select>
      <input class="form-control vl-nombre" placeholder="Nombre del producto" style="display:none;margin-top:6px">
    </div>
    <div class="vl-cant">
      <label class="form-label">Cantidad</label>
      <div class="stepper">
        <button type="button" class="stepper-btn" data-d="-1" aria-label="Menos">−</button>
        <input class="form-control vl-cantidad" type="number" min="1" step="1" value="1" inputmode="numeric">
        <button type="button" class="stepper-btn" data-d="1" aria-label="Más">+</button>
      </div>
    </div>
    <div class="vl-precio">
      <label class="form-label">Precio c/u</label>
      <input class="form-control vl-precio-input" type="number" min="0" step="100" inputmode="numeric" placeholder="0">
    </div>
    <div class="vl-sub"><span class="vl-subtotal">$0</span>
      <button type="button" class="icon-btn vl-quitar" aria-label="Quitar producto">✕</button>
    </div>
    <input type="hidden" class="vl-costo">`;
  cont.appendChild(div);

  const sel = div.querySelector('.vl-select');
  sel.addEventListener('change', () => {
    const p = catalogoVenta.find(x => String(x.id) === sel.value);
    div.querySelector('.vl-nombre').style.display = sel.value === 'otro' ? 'block' : 'none';
    if (p) {
      div.querySelector('.vl-precio-input').value = p.precio_venta;
      div.querySelector('.vl-costo').value = p.costo;
    } else {
      div.querySelector('.vl-costo').value = '';
      if (sel.value === 'otro') div.querySelector('.vl-nombre').focus();
    }
    recalcularVenta();
  });
  div.querySelectorAll('.stepper-btn').forEach(b => b.addEventListener('click', () => {
    const inp = div.querySelector('.vl-cantidad');
    inp.value = Math.max(1, (parseInt(inp.value) || 1) + Number(b.dataset.d));
    recalcularVenta();
  }));
  div.querySelectorAll('input').forEach(i => i.addEventListener('input', recalcularVenta));
  div.querySelector('.vl-quitar').addEventListener('click', () => {
    if (cont.children.length > 1) { div.remove(); recalcularVenta(); }
  });

  if (!catalogoVenta.length) { sel.value = 'otro'; sel.dispatchEvent(new Event('change')); }
  if (productoId) { sel.value = String(productoId); sel.dispatchEvent(new Event('change')); }
  recalcularVenta();
}

function lineasVenta() {
  return [...document.querySelectorAll('#mv-lineas .venta-linea')].map(div => {
    const sel = div.querySelector('.vl-select').value;
    const costo = div.querySelector('.vl-costo').value;
    return {
      producto_id: sel && sel !== 'otro' ? Number(sel) : null,
      nombre: sel === 'otro' ? div.querySelector('.vl-nombre').value.trim() : null,
      elegido: !!sel,
      cantidad: parseInt(div.querySelector('.vl-cantidad').value) || 0,
      precio_unitario: div.querySelector('.vl-precio-input').value === '' ? null : Number(div.querySelector('.vl-precio-input').value),
      costo_unitario: costo === '' ? null : Number(costo),
      div,
    };
  });
}

function recalcularVenta() {
  let total = 0, ganancia = 0;
  lineasVenta().forEach(l => {
    const sub = (l.precio_unitario || 0) * l.cantidad;
    total += sub;
    ganancia += sub - (l.costo_unitario || 0) * l.cantidad;
    l.div.querySelector('.vl-subtotal').textContent = fmt(sub);
  });
  document.getElementById('mv-total').textContent = fmt(total);
  const g = document.getElementById('mv-ganancia');
  g.textContent = fmt(ganancia);
  g.style.color = ganancia >= 0 ? 'var(--green)' : 'var(--red)';
}

async function guardarVenta() {
  const lineas = lineasVenta();
  for (const l of lineas) {
    if (!l.elegido) return toast('Elige el producto vendido', 'error');
    if (!l.producto_id && !l.nombre) return toast('Escribe el nombre del producto', 'error');
    if (l.cantidad < 1) return toast('La cantidad debe ser al menos 1', 'error');
    if (l.precio_unitario === null) return toast('Indica el precio de venta', 'error');
  }
  const body = {
    fecha: document.getElementById('mv-fecha').value,
    items: lineas.map(({ div, elegido, ...l }) => l),
  };
  await conCarga(document.getElementById('mv-guardar'), async () => {
    try {
      const d = await api('/api/ventas', { method: 'POST', body });
      closeModal('modal-venta');
      toast(`Venta de ${fmt(d.total)} guardada · ganancia ${fmt(d.ganancia)}`, 'success');
      (d.avisos || []).forEach(a => toast(a, 'warning', 6000));
      document.dispatchEvent(new CustomEvent('venta-registrada', { detail: d }));
    } catch (e) {
      toast(e.message, 'error');
    }
  }, 'Guardando...');
}
