// ─── UTILIDADES GLOBALES ───────────────────────────────────────────────────

/**
 * Formatea número como moneda colombiana
 */
function fmt(n) {
  if (n === null || n === undefined || isNaN(n)) return '$0';
  return '$' + Number(n).toLocaleString('es-CO', { maximumFractionDigits: 0 });
}

/**
 * Toast notification sistema
 */
function toast(msg, type = 'info', duration = 3500) {
  const container = document.getElementById('toast-container');
  if (!container) return;

  const icons = { success: '✅', error: '❌', info: 'ℹ️', warning: '⚠️' };
  const t = document.createElement('div');
  t.className = `toast ${type}`;
  t.innerHTML = `<span>${icons[type] || 'ℹ️'}</span><span>${msg}</span>`;
  container.appendChild(t);

  setTimeout(() => {
    t.style.animation = 'slideIn 0.3s ease reverse';
    setTimeout(() => t.remove(), 300);
  }, duration);
}

/**
 * Cierra cualquier modal
 */
function closeModal(id) {
  const el = document.getElementById(id);
  if (el) el.classList.remove('open');
}

// Cerrar modal al hacer clic fuera
document.addEventListener('click', (e) => {
  if (e.target.classList.contains('modal-overlay')) {
    e.target.classList.remove('open');
  }
});

// Cerrar modal con ESC
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    document.querySelectorAll('.modal-overlay.open').forEach(m => m.classList.remove('open'));
  }
});

// ─── ANIMACIONES DE ENTRADA ────────────────────────────────────────────────

/**
 * Anima números contando desde 0 hasta el valor final
 */
function animateNumber(el, endVal, prefix = '$', duration = 800) {
  if (!el) return;
  const start = performance.now();
  const startVal = 0;

  function update(time) {
    const elapsed = time - start;
    const progress = Math.min(elapsed / duration, 1);
    // easeOutExpo
    const eased = progress === 1 ? 1 : 1 - Math.pow(2, -10 * progress);
    const current = Math.floor(startVal + (endVal - startVal) * eased);
    el.textContent = prefix + Number(current).toLocaleString('es-CO');
    if (progress < 1) requestAnimationFrame(update);
  }

  requestAnimationFrame(update);
}

// ─── CHART.JS DEFAULTS ─────────────────────────────────────────────────────

if (typeof Chart !== 'undefined') {
  Chart.defaults.font.family = "'Inter', -apple-system, sans-serif";
  Chart.defaults.color = '#86868b';
  Chart.defaults.plugins.tooltip.padding = 10;
  Chart.defaults.plugins.tooltip.cornerRadius = 8;
  Chart.defaults.plugins.legend.labels.usePointStyle = true;
  Chart.defaults.plugins.legend.labels.pointStyleWidth = 8;
  Chart.defaults.animation.duration = 700;
  Chart.defaults.animation.easing = 'easeOutQuart';
}

// ─── DRAG & DROP GLOBAL ────────────────────────────────────────────────────

document.querySelectorAll('.upload-zone').forEach(zone => {
  zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('drag-over'); });
  zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'));
  zone.addEventListener('drop', e => {
    e.preventDefault();
    zone.classList.remove('drag-over');
    const file = e.dataTransfer.files[0];
    const input = zone.querySelector('input[type=file]');
    if (file && input) {
      const dt = new DataTransfer();
      dt.items.add(file);
      input.files = dt.files;
      input.dispatchEvent(new Event('change'));
    }
  });
});

// ─── RESPONSIVE SIDEBAR ────────────────────────────────────────────────────

function toggleSidebar() {
  const s = document.getElementById('sidebar');
  if (s) s.classList.toggle('open');
}

// ─── ACTIVE NAV ────────────────────────────────────────────────────────────

document.querySelectorAll('.nav-item').forEach(el => {
  if (el.getAttribute('href') === location.pathname) {
    el.classList.add('active');
  }
});
