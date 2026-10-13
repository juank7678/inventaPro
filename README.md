# Inventa

Ventas, ganancias y productos de un negocio pequeño, claros todos los días y desde el celular.

- Registrar ventas en segundos (con uno o varios productos)
- Ganancia y margen por producto, producto estrella, comparación con el mes pasado
- Meta mensual con avance diario
- Punto de equilibrio, escenarios y pronóstico de ventas
- Reportes en Excel y PDF por período
- Stock opcional con avisos de reposición

El diagnóstico completo de la versión anterior y de los cambios está en [DIAGNOSTICO.md](DIAGNOSTICO.md).

## Ejecutar en tu computador

```bash
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python app.py
```

Abre <http://127.0.0.1:5000>. La primera vez se crea el usuario `admin@inventa.com` y la app pide cambiar la contraseña
(o usa `ADMIN_EMAIL` y `ADMIN_PASSWORD` para definirlo).

## Variables de entorno

| Variable | Para qué sirve |
|---|---|
| `DATABASE_URL` | Base Postgres permanente (Supabase, Neon, Render). **Obligatoria en producción**: sin ella se usa SQLite y en Render los datos se borran al reiniciar. |
| `SECRET_KEY` | Firma las sesiones. Render la genera sola con `render.yaml`. |
| `ADMIN_EMAIL`, `ADMIN_PASSWORD` | Usuario administrador que se crea si la base está vacía. |
| `ADMIN_NOMBRE`, `EMPRESA` | Nombre de la persona y del negocio para ese primer usuario. |
| `APP_TZ` | Zona horaria del negocio (por defecto `America/Bogota`). |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `ALERT_EMAIL`, `ALERT_EMAIL_PASS`, `ALERT_DEST_EMAIL` | Opcionales: avisos de stock bajo por Telegram o correo. |

## Despliegue en Render

`render.yaml` ya define el servicio. Después de conectar el repositorio, completa en *Environment*
`DATABASE_URL`, `ADMIN_EMAIL` y `ADMIN_PASSWORD`. Los pasos para crear la base en Supabase están en
[DIAGNOSTICO.md](DIAGNOSTICO.md#lo-que-falta-hacer-requiere-acción-tuya).
