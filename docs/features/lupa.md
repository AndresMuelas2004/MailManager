# Características de la lupa de búsqueda — comportamiento (MVP)

Este documento describe **qué hace** la lupa cuando un usuario la usa, sin entrar en código. Es una guía de comportamiento para que cualquier persona del equipo entienda cómo se va a comportar la funcionalidad cuando se siente delante de la app.

---

## 1. Qué busca la lupa y dónde

- La lupa filtra los correos que **ya están sincronizados** en la base de datos local de MailManager. **No llama a Gmail ni a Outlook** — solo mira lo que ya tenemos guardado.
- Busca en tres campos de cada correo:
  - **Asunto** del correo (`subject`).
  - **Email del remitente** (`sender_email`).
  - **Nombre del remitente** (`sender_name`).
- Para que un correo aparezca en los resultados basta con que **una sola** de esas tres columnas contenga lo que el usuario escribió.

---

## 2. Qué grado de "inteligencia" tiene la búsqueda

La búsqueda del MVP es **literal con dos relajaciones**: el texto escrito tiene que aparecer tal cual en alguno de los tres campos, pero ignorando mayúsculas/minúsculas y tildes.

### Lo que sí encuentra

- **Coincidencia en cualquier posición** de la cadena. Si el usuario escribe `fact`, encuentra correos cuyo asunto sea `Factura`, `Refactura 2024` o `Esto es una factura`. No hace falta que la palabra empiece por lo escrito.
- **Sin distinguir mayúsculas/minúsculas**. Escribir `JUAN`, `juan` o `Juan` da exactamente los mismos resultados.
- **Sin distinguir tildes/acentos**. Escribir `jose` encuentra `José`; `accion` encuentra `acción`; `maria` encuentra `María`. Esto es imprescindible para usar la app en español.

### Lo que NO encuentra (limitaciones aceptadas para el MVP)

- **Errores tipográficos**: si el usuario escribe `facutra` (con las letras cambiadas), **no** encuentra `factura`. Hay que escribirlo bien.
- **Variantes de la misma palabra**: escribir `facturas` (plural) **no** encuentra `factura` (singular); `comprar` **no** encuentra `compra` ni `comprado`. La búsqueda es por letras exactas, no por raíz de palabra.
- **Sinónimos o significado**: escribir `pedido` **no** encuentra correos que hablan de `compra` u `orden`. La lupa no entiende qué significa lo que escribes, solo busca las letras exactas.

> Estas tres limitaciones se documentan a propósito como aceptadas para el MVP. Si más adelante los usuarios reportan que necesitan tolerancia a typos o búsqueda por raíz de palabra, hay un plan de fases futuras para añadirlo.

---

## 3. Cuándo se dispara la búsqueda (debounce de 300 ms + mínimo 2 caracteres)

La lupa **no lanza una búsqueda por cada letra** que el usuario teclea. Sería un derroche de tráfico y crearía una experiencia "pegajosa". En su lugar, sigue estas reglas:

### Las tres condiciones que se tienen que cumplir a la vez

Una búsqueda **solo** se lanza cuando ocurren las tres cosas simultáneamente:

1. **Ha habido un cambio en el input** — el usuario ha tecleado o borrado al menos un carácter.
2. **Han pasado 300 ms sin que el usuario vuelva a tocar el teclado** — pausa natural entre palabras.
3. **El texto escrito tiene al menos 2 caracteres** — cualquier tipo de carácter cuenta (letras, números, símbolos, acentos).

Si falla cualquiera de las tres, **no se hace ninguna búsqueda**.

### Paso a paso de lo que ve el usuario

- **Usuario escribe 1 carácter**: no pasa nada (queda por debajo de 2). Ve el listado completo del buzón sin filtrar.
- **Usuario escribe el 2º carácter**: arranca un cronómetro interno de 300 ms.
- **Usuario sigue tecleando antes de los 300 ms**: el cronómetro se cancela y arranca uno nuevo desde cero. La búsqueda anterior nunca llega a salir.
- **Usuario hace una pausa de 300 ms**: ahí sí, se lanza **una sola** búsqueda con el texto actual y se actualizan los resultados en pantalla.
- **Usuario borra hasta dejar menos de 2 caracteres** (o vacía el input por completo): la lupa **deja de filtrar** y vuelve a mostrar el listado completo del buzón en el que estaba. No se queda esperando — limpia el filtro de forma activa.
- **Usuario hace clic en un correo de los resultados**: abre ese correo normalmente. La lupa no interfiere.
- **Usuario vuelve a teclear**: se reinicia el ciclo desde el principio.

### Por qué 300 ms

- Es imperceptible: más corto que la pausa natural entre palabras al escribir.
- Es el estándar del sector: Google, Gmail, GitHub, Slack, Notion y Linear usan entre 200 y 300 ms.
- Más corto (50-100 ms) generaría peticiones innecesarias mientras el usuario sigue tecleando.
- Más largo (500+ ms) introduciría un lag perceptible.

### Por qué mínimo 2 caracteres

Una sola letra (`a`, `e`, `s`...) coincidiría con prácticamente todos los correos del buzón y la búsqueda sería inútil. Con 2 caracteres ya hay suficiente especificidad para que los resultados sean útiles.

---

## 4. Búsqueda con varias palabras

Si el usuario escribe **más de una palabra** separada por espacios (ej. `juan factura`), la lupa trata cada palabra como un **token independiente** y exige que **cada token aparezca en alguna de las tres columnas** del correo (no necesariamente en la misma). Es exactamente lo que hace Google o Gmail.

### Ejemplos con `juan factura`

- ✅ Encuentra: un correo cuyo asunto es `"Factura de Juan"`.
- ✅ Encuentra: un correo cuyo asunto es `"Juan envió la factura"`.
- ✅ Encuentra: un correo cuyo remitente se llama `"Juan"` y cuyo asunto es `"factura mensual"` — el token `juan` casa con el nombre del remitente y el token `factura` con el asunto.
- ❌ No encuentra: un correo cuyo asunto es `"Factura de Pedro"` — falta el token `juan`.
- ❌ No encuentra: un correo cuyo remitente se llama `"Juan"` y cuyo asunto es `"Hola"` — falta el token `factura`.

### El orden no importa

Escribir `juan factura` y `factura juan` da exactamente los mismos resultados. Lo único que cuenta es que **todos los tokens estén presentes** en algún sitio del correo.

### Tope de seguridad

Si el usuario pega un texto muy largo, solo se consideran los **primeros 10 tokens**. Es una salvaguarda para evitar consultas patológicas y, en la práctica, nadie busca con más de 10 palabras.

---

## 5. Alcance de la búsqueda dentro de la app

La lupa **respeta el contexto donde está el usuario**. No busca a lo loco por toda la app.

### Solo en el buzón actual

La lupa filtra dentro del **box** donde el usuario está mirando los correos:

- Si está en `ALL_MAIL` (bandeja principal), la lupa busca solo en correos de esa bandeja.
- Si está en `SENT` (enviados), busca solo en enviados.
- Si está en `SPAM`, solo en spam.
- Si está en `TRASH` (papelera), solo en la papelera.

Para buscar en otra bandeja, el usuario tiene que **cambiar de buzón** y volver a usar la lupa. Es el comportamiento natural y el mismo que hace Gmail por defecto.

### Multi-cuenta: hereda el comportamiento del listado

MailManager soporta varios correos por mailbox (vista unificada). La lupa hereda el mismo modo en el que se está viendo la bandeja:

- **Vista unificada del mailbox** (sin cuenta concreta seleccionada): la lupa busca en **todas las cuentas** del mailbox a la vez.
- **Vista de una cuenta concreta**: la lupa busca **solo en esa cuenta**.

El usuario no tiene que configurar nada — funciona como ya está acostumbrado a ver la bandeja.

---

## 6. Cómo se muestran los resultados

- Los resultados aparecen en la **misma tabla de correos** que el usuario ya estaba viendo. La pantalla no cambia, simplemente la lista se "filtra" mostrando solo los que casan.
- Los resultados están **ordenados por fecha de recepción descendente** (los más recientes primero), igual que el listado normal del buzón.
- **No hay ordenación por relevancia**. Un correo donde la palabra buscada aparece 5 veces no sale antes que uno donde aparece solo 1 vez. Lo único que decide el orden es la fecha.
- Por defecto se muestran hasta **200 correos** en una sola carga. Es de sobra para el caso de uso típico (búsquedas concretas que devuelven pocos resultados).
- En el MVP **no hay scroll infinito**. Si una búsqueda devuelve más de 200 correos, el usuario verá los 200 más recientes que casan. Si esto se vuelve un problema en el día a día, se evaluará añadir scroll en una fase posterior.

---

## 7. Qué pasa "por debajo" mientras el usuario escribe (resumen rápido)

Para entender el flujo completo de un vistazo:

1. Usuario escribe en la lupa → se actualiza el texto en pantalla (sin tocar la red todavía).
2. Si supera los 2 caracteres y deja de escribir 300 ms → el navegador hace **una única petición** al backend de MailManager.
3. El backend consulta la base de datos local (PostgreSQL) y devuelve los correos que casan con todas las reglas anteriores.
4. La tabla de correos se repinta con los resultados.
5. Si el usuario hace clic en un correo, lo abre normalmente.
6. Si el usuario vuelve a escribir o borrar, todo el ciclo empieza de nuevo.

Si llega una respuesta de una búsqueda antigua justo cuando el usuario ya estaba escribiendo otra cosa, esa respuesta se **descarta automáticamente** para que nunca pisen los resultados de la búsqueda más reciente.

---

## 8. Resumen en una frase

> La lupa es un filtro **local, literal, en el buzón actual, con normalización de mayúsculas y tildes, que se dispara tras una pausa de 300 ms cuando el texto tiene al menos 2 caracteres, exige que todas las palabras del usuario aparezcan en alguno de los tres campos del correo, y muestra hasta 200 resultados ordenados por fecha**.

Eso es todo lo que necesita saber un programador (o cualquier persona del equipo) para entender cómo se va a comportar la lupa en el MVP.
