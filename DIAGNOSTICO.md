# Diagnóstico de Inventa Pro

Fecha: 12 de octubre de 2026 · Versión revisada: commit `5ccad84` (abril 2026)

Inventa Pro es una aplicación Flask (un solo `app.py`, plantillas Jinja, Chart.js) para controlar ventas,
productos, ganancias y proyecciones de un negocio pequeño. Se revisó todo el código con un objetivo concreto:
que sirva para el día a día de un emprendimiento que vende productos, sobre todo desde el celular.

## Resumen

La base era buena: los cálculos de margen, punto de equilibrio y escenarios están bien planteados, y el
diseño oscuro se ve profesional. Pero la app estaba pensada como **demo**, no para usarla con datos reales:

1. **Los datos se pierden.** En Render (plan gratuito) la base SQLite vive en un disco temporal que se borra en
   cada reinicio o despliegue, y el plan gratuito se reinicia cada vez que la app queda inactiva unos 15 minutos.
2. **Cualquiera podía entrar.** La contraseña del administrador estaba publicada en la pantalla de login,
   en la página de presentación y en una imagen del repositorio.
3. **No había forma de registrar una venta a mano.** Solo se podían subir ventas desde Excel.
4. **En el celular no se podía navegar**: el menú lateral desaparecía y no había botón para abrirlo.

Todo lo anterior quedó corregido, salvo el punto 1, que requiere crear una base de datos externa
(ver “Lo que falta hacer”). La app ya está preparada para usarla.

## Hallazgos y lo que se hizo

### Críticos (seguridad y pérdida de datos)

| # | Problema | Qué se hizo |
|---|----------|-------------|
| 1 | Datos guardados en SQLite sobre disco temporal de Render: se borran en cada reinicio. | Soporte para `DATABASE_URL` (Postgres: Supabase, Neon, Render). Aviso rojo visible para el administrador mientras no esté configurada. |
| 2 | Contraseña `inventa2024` publicada en login, landing (`index.html`) e imagen `Credenciales.JPG`. | Se quitaron de las tres partes. Las claves conocidas obligan a cambiar la contraseña al entrar. El administrador inicial se crea desde `ADMIN_EMAIL` / `ADMIN_PASSWORD`. |
| 3 | `SECRET_KEY` escrita en el código y en `render.yaml` (repositorio público): permite falsificar sesiones. | Se lee del entorno; Render la genera automáticamente (`generateValue`). En local se crea una aleatoria en `instance/`. |
| 4 | `/api/config` dejaba que cualquier usuario se cambiara el rol a administrador. | Ya no se puede cambiar el rol desde ahí. |
| 5 | `/api/config` permitía cambiar el servidor de correo de alertas desde el navegador. | Las alertas solo se configuran con variables de entorno. |
| 6 | “Cargar demo” estaba en el inicio, al lado de “Actualizar”, y **borraba todas las ventas reales** sin preguntar ni revisar el rol. | Movido a *Mi cuenta → Zona de datos*, solo administrador, y pide escribir BORRAR si ya hay ventas. Lo mismo para “Borrar todo”. |
| 7 | Nombres de productos insertados en la página sin escapar (inyección de código / XSS). | Todo el texto se escapa antes de mostrarse. |
| 8 | Sin protección CSRF en la API. | Las peticiones que modifican datos exigen un encabezado que otro sitio no puede enviar; cookies `SameSite=Lax`, `HttpOnly` y `Secure` en producción. |
| 9 | Roles (admin / vendedor / consultor) declarados pero verificados en un solo endpoint. | Verificados en todos: el consultor solo ve, el vendedor registra ventas y productos, el administrador hace todo. |
| 10 | Sin límite de intentos de login. | Bloqueo de 5 minutos tras 8 intentos fallidos. |

### Errores de funcionamiento

| # | Problema | Qué se hizo |
|---|----------|-------------|
| 11 | La página **Reportes** llamaba a `/api/reporte-data`, que no existía: la página fallaba. | Endpoint creado. |
| 12 | Los reportes Excel/PDF ignoraban el período elegido y exportaban todo el historial. | Ahora respetan el período (hoy, semana, mes, mes pasado, año, todo o fechas a elección). |
| 13 | “Vs mes anterior” comparaba los días que van del mes contra el mes anterior **completo** (el día 5 siempre mostraba −80 %). | Compara los mismos días: 1–12 de octubre contra 1–12 de septiembre. |
| 14 | “Hoy” se calculaba con la hora del servidor (UTC): desde las 7 p. m. de Colombia las ventas quedaban en el día siguiente. | Zona horaria `America/Bogota` (configurable con `APP_TZ`). |
| 15 | Si el Excel no traía costo, se **inventaba** como 60 % del precio: ganancias ficticias. | Se toma el costo del catálogo; si no existe, se avisa cuántas ventas quedaron sin costo. |
| 16 | Las filas con errores del Excel se descartaban en silencio. | Se informa qué filas fallaron y por qué. Se aceptan números como `45.000` o `$45.000`, fechas `15/09/2026` y archivos CSV. |
| 17 | El botón “Descargar plantilla” generaba un CSV que el sistema no aceptaba. | Plantillas reales en Excel, y el sistema acepta también CSV. |
| 18 | El análisis de inventario mostraba `precio_liquidacion`, un campo que la API no enviaba (“$0”). | Corregido. |
| 19 | `productos.html` tenía un documento HTML dentro de otro (estructura inválida). | Reescrita. |
| 20 | El pronóstico rellenaba con ceros los días anteriores al inicio del negocio y usaba umbrales fijos de confianza (en pesos). | Usa solo días reales, exige 10 días con ventas, tendencia amortiguada y confianza según el error relativo. |
| 21 | La proyección promediaba los precios del catálogo como si todos los productos se vendieran igual. | Pondera por lo que realmente se vendió en los últimos 60 días. |
| 22 | “Producto estrella” = el que más factura, y “a mejorar” comparaba montos exactos. | Estrella = el que más **ganancia** deja; además “más vendido” y “menor ganancia” por separado. |
| 23 | Las ventas en la página Ventas mostraban “Hoy” marcado pero cargaban el mes. | Corregido. |
| 24 | La meta mensual se guardaba pero no se usaba. | Ahora se ve en el inicio con barra de avance y proyección de cierre de mes. |
| 25 | Al renombrar un producto se perdía su historial (las ventas guardan el nombre). | Al renombrar se actualizan sus ventas. |
| 26 | Dependencias sin versión mínima y librerías que no se usaban (`apscheduler`, `scipy` explícito). | `requirements.txt` con rangos de versión; scheduler retirado (en producción ya estaba apagado). |

### Funciones nuevas

- **Registrar venta en segundos** desde cualquier página (botón “Registrar venta” o el “+” en el celular):
  se elige el producto, el precio se llena solo, se ajusta la cantidad y muestra total y ganancia antes de guardar.
  Permite varios productos en una misma venta y productos que no estén en el catálogo.
- **Historial de ventas** con opción de eliminar una venta equivocada (devuelve las unidades al stock).
- **Mi cuenta**: cambiar contraseña, datos del negocio, meta mensual, inversión inicial,
  agregar personas con acceso (con rol) y zona de datos protegida.
- **Inicio renovado**: vendido hoy (vs. ayer), mes (vs. mismos días del mes pasado), ganancia, meta,
  ganancia después de gastos, lo más vendido, lectura rápida (estrella, más vendido, margen bajo,
  productos sin ventas) y últimas ventas. Guía de “primeros pasos” cuando el negocio está vacío.
- **Stock opcional**: si se vende por encargo, se deja el stock en 0 y no aparecen alertas.
- Reportes con **ganancia después de gastos** (estimada) y ticket promedio.

### Mejoras visuales

- Diseño pensado para el celular: barra de navegación inferior con botón “+” central, menú lateral deslizable,
  formularios tipo hoja inferior, tablas con desplazamiento horizontal y rejillas que se apilan.
- Más contraste en textos secundarios (antes casi no se leían sobre el fondo negro).
- Confirmaciones con ventana propia en lugar de las del navegador, avisos (toasts) más claros,
  estados vacíos que explican qué hacer, cálculo de margen en vivo al crear productos.
- Lenguaje sencillo: “Lo que te cuesta”, “Ganas por unidad”, “Vendido hoy”, en lugar de jerga contable.

## Verificación

Se probó con un cliente de pruebas sobre una copia de la base local y en el navegador (escritorio y celular 375 px):
login, cambio obligatorio de contraseña, registro de venta (uno y varios productos, producto fuera de catálogo,
fecha futura rechazada), eliminación de venta, importación de Excel/CSV con errores, creación/renombrado de productos,
duplicados, gastos, proyección, pronóstico, reportes Excel/PDF por período, comparativo mensual, roles
(consultor sin permisos de escritura), bloqueo CSRF y API sin sesión.

## Lo que falta hacer (requiere acción tuya)

1. **Conectar la base de datos permanente (lo más importante).** Sin esto, todo lo que registre tu hija
   se borra cuando Render reinicia la app.
   - ✅ Ya creada (12/10/2026): proyecto Supabase `inventa-pro` (plan gratuito, región us-west-1), con un usuario
     exclusivo `inventa_app` y un esquema privado `inventa` que no queda expuesto en la API pública de Supabase.
     Probada con la app completa y dejada vacía.
   - La cadena de conexión está en `instance/DATABASE_URL_para_Render.txt` (solo en el computador; no se sube a GitHub).
   1. En Render → servicio *inventa* → *Environment*, agregar `DATABASE_URL` con el contenido de ese archivo.
   2. Agregar también `ADMIN_EMAIL` (el correo de tu hija) y `ADMIN_PASSWORD` (una clave temporal).
   3. Guardar: Render redespliega y crea el usuario administrador.
   - Ojo: Supabase pausa los proyectos gratuitos tras 7 días sin actividad. Con uso diario no pasa; si ocurre,
     se reactiva desde el panel de Supabase sin perder datos.
2. **Entrar y cambiar la contraseña** en *Mi cuenta*. Si no se definió `ADMIN_PASSWORD`, el usuario inicial es
   `admin@inventa.com` con la clave anterior y la app obliga a cambiarla en el primer ingreso.
3. **Cargar los productos reales** (uno por uno o con la plantilla de Excel) con su costo, y poner la meta mensual.
4. El plan gratuito de Render “se duerme”: la primera visita después de un rato tarda unos 30–50 segundos.

## Recomendaciones a futuro

- Todos los usuarios ven los mismos datos (un solo negocio). Si quieres que otra persona use la app para
  otro emprendimiento, conviene desplegar una copia aparte o agregar separación por negocio.
- Importar el mismo Excel dos veces duplica las ventas; para el día a día es mejor registrar cada venta en la app.
- Agregar clientes (a quién se vendió) y medio de pago serían las siguientes funciones con más valor.
- Respaldos: descarga el reporte Excel con el período “Todo” una vez al mes y guárdalo; es una copia completa de ventas y productos.
- Existe también el proyecto `Emprender` (sin inventario) iniciado en septiembre; esta versión de Inventa Pro
  cubre el mismo uso con stock opcional, así que conviene decidir cuál seguir para no mantener dos.
