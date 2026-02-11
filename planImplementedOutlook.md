# Plan: Implementación completa del cliente Outlook

## Contexto

El cliente Outlook (`OutlookClient`) existía pero solo tenía `authenticate()` implementado (con imports inline y patrones inconsistentes). Los métodos `authenticate_silent`, `fetch_unread_emails` y `send_email` lanzaban `NotImplementedError`. Además, toda la capa de storage/services estaba hardcodeada para Gmail. Este cambio convierte Outlook en un ciudadano de primera clase, elimina `ProviderNotSupported`/`NotImplementedError`, y hace la infraestructura provider-aware.

---

## Paso 1 — Eliminar `ProviderNotSupported` y `EmailProviderNotSupportedError`

Dado que los proveedores se eligen desde un desplegable de opciones soportadas, estos errores no tienen sentido.

### `backend/core/email/errors.py`
- Eliminar la clase `EmailProviderNotSupportedError`.

### `backend/api/errors/exceptions.py`
- Eliminar la clase `ProviderNotSupported`.

### `backend/api/errors/__init__.py`
- Eliminar `ProviderNotSupported` del import y de `__all__`.

### `backend/api/errors/handlers.py`
- Eliminar `ProviderNotSupported` del import.
- Eliminar `ProviderNotSupported` de `_STATUS_MAP`.

### `backend/api/services/services_helpers.py`
- Eliminar `EmailProviderNotSupportedError` del import.
- Eliminar `ProviderNotSupported` del import.
- Eliminar la entrada `(EmailProviderNotSupportedError, ProviderNotSupported)` de `_CORE_TO_API_MAP`.

### `backend/api/storage/token_store.py`
- Eliminar `ProviderNotSupported` del import.
- En `_token_path_for_account`: reemplazar los `raise ProviderNotSupported(...)` por `raise AccountMisconfigured(...)` como fallback para proveedores desconocidos.

---

## Paso 2 — Hacer `token_store.py` provider-aware

### `backend/api/storage/token_store.py`

**`_token_path_for_account(record)`** — Añadir rama Outlook. Ambos proveedores comparten el directorio de tokens (`$MIA_TOKEN_PATH`), diferenciándose solo en el prefijo del nombre de archivo:
```python
token_dir = os.getenv("MIA_TOKEN_PATH")

if provider == "gmail":
    return Path(token_dir) / f"gmail_token_{account_label}.json"

if provider == "outlook":
    return Path(token_dir) / f"outlook_token_{account_label}.json"
```
Para proveedor desconocido: `raise AccountMisconfigured(f"Unknown provider '{provider}'.")`.

**`load_app_credentials(provider: str)`** — Añadir parámetro `provider`. Un diccionario `_ENV_CREDENTIALS` mapea cada proveedor a su variable de entorno de credenciales:
- `"gmail"` → `MIA_GMAIL_CREDENTIALS_PATH`, extrae bloque `"installed"`/`"web"`.
- `"outlook"` → `MIA_OUTLOOK_CREDENTIALS_PATH`, retorna el dict directamente (sin bloques installed/web).
- Otro → `raise AccountMisconfigured(...)`.

**`load_account_tokens(mailbox_id, account_id, provider)`** — Añadir parámetro `provider`:
- Construir record con el provider recibido en vez de hardcodear `"gmail"`.

**`save_account_tokens(mailbox_id, account_id, provider, token_data)`** — Añadir parámetro `provider`:
- Construir record con el provider recibido en vez de hardcodear `"gmail"`.

---

## Paso 3 — Actualizar `services_helpers.py` provider-aware

### `backend/api/services/services_helpers.py`

**`load_wrapped_app_credentials(provider: str)`** — Añadir parámetro `provider`:
```python
def load_wrapped_app_credentials(provider: str) -> dict[str, Any]:
    credentials = load_app_credentials(provider)
    payload = dict(credentials) if isinstance(credentials, dict) else {}
    if "client_secret" in payload:
        payload["client_secret"] = _wrap_secret(payload.get("client_secret"))
    return payload
```

**`load_wrapped_account_tokens(mailbox_id, account_id, provider)`** — Añadir parámetro `provider`:
```python
def load_wrapped_account_tokens(mailbox_id: str, account_id: str, provider: str) -> dict[str, Any]:
    token_data = load_account_tokens(mailbox_id, account_id, provider)
    ...
```

---

## Paso 4 — Actualizar `accounts_service.py`

### `backend/api/services/accounts_service.py`

**`connect_account()`**:
- Obtener provider del record: `provider = record.get("provider", "")`.
- Pasar provider a la carga de credenciales: `app_credentials = load_wrapped_app_credentials(provider)`.
- Pasar provider al guardado de tokens: `save_account_tokens(mailbox_id, account_id, provider, token_payload)`.

---

## Paso 5 — Actualizar `emails_service.py`

### `backend/api/services/emails_service.py`

**`get_unread()`**:
- Cachear `app_credentials` por provider para evitar lecturas redundantes del disco:
```python
credentials_cache: dict[str, dict[str, Any]] = {}
for account in accounts:
    provider = str(account.get("provider") or "").lower()
    if provider not in credentials_cache:
        credentials_cache[provider] = load_wrapped_app_credentials(provider)
    app_credentials = credentials_cache[provider]
    user_tokens = load_wrapped_account_tokens(mailbox_id, account_id, provider)
    ...
```
- `label_lookup` pasa a ser `dict[str, tuple[str, str, str]]` → `(mailbox_id, account_id, provider)`.

**`send_email()`**:
- Obtener provider del account record.
- `app_credentials = load_wrapped_app_credentials(provider)`.
- `user_tokens = load_wrapped_account_tokens(mailbox_id, payload.account_id, provider)`.
- `label_lookup` incluye provider.

**`_persist_refreshed_tokens()`**:
- Firma actualizada: `label_lookup: dict[str, tuple[str, str, str]]`.
- Desempaquetar: `mailbox_id, account_id, provider = ids`.
- Llamar: `save_account_tokens(mailbox_id, account_id, provider, payload)`.

---

## Paso 6 — Simplificar `EmailManager._build_client`

### `backend/core/email/email_manager.py`

**`_build_client()`**:
- Outlook ya no necesita config (las credenciales vienen del archivo apuntado por la variable de entorno):
```python
if provider == "outlook":
    return OutlookClient(account_label=account_label)
```
- Para proveedor desconocido: `raise EmailProviderConfigError(f"Unknown provider '{provider}'.")`.
- Eliminar import de `EmailProviderNotSupportedError`.

---

## Paso 7 — Reescribir `OutlookClient` completo

### `backend/core/email/outlook_client.py`

**Imports a nivel de módulo** (eliminados los imports inline):
```python
import json
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Any, List
from pydantic import SecretStr
from .email_client import EmailClient, EmailMessage
from .errors import (
    EmailMissingAppCredentialsError,
    EmailMissingRefreshTokenError,
    EmailMissingTokenError,
    EmailNotAuthenticatedError,
    EmailRecipientsMissingError,
    EmailRefreshFailedError,
)
```

**Constantes**:
```python
OUTLOOK_SCOPES = [
    "https://graph.microsoft.com/Mail.ReadWrite",
    "https://graph.microsoft.com/Mail.Send",
    "offline_access",
]
GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
```

**Constructor simplificado** (igual que Gmail, solo `account_label`):
```python
def __init__(self, account_label: str = "outlook") -> None:
    self._account_label = account_label
    self._access_token: str | None = None
```

**Métodos helper** (mismos patrones que Gmail):
- `_unwrap_app_credentials(app_credentials)` — idéntico a Gmail.
- `_unwrap_user_tokens(user_tokens)` — idéntico a Gmail.
- `_wrap_account_tokens(token_data)` — idéntico a Gmail.
- `_parse_expiry(value)` — idéntico a Gmail.
- `_resolve_scopes(credentials_payload, token_payload=None)` — resuelve scopes desde credenciales o tokens, con fallback a `OUTLOOK_SCOPES`.
- `_token_url(tenant)` — construye la URL del endpoint de tokens de Microsoft.
- `_compute_expiry(expires_in_raw)` — calcula la fecha de expiración a partir de `expires_in` en segundos.
- `_graph_request(method, url, body=None)` — helper para llamadas autenticadas a Microsoft Graph API.
- `_token_request(token_url, payload)` — helper para llamadas al endpoint de tokens de Microsoft (reutilizado por `authenticate` y `authenticate_silent`).

**`authenticate(app_credentials)`** — Refinado:
- Imports específicos del flujo interactivo (`base64`, `hashlib`, `secrets`, `threading`, `webbrowser`, `http.server`) se mantienen locales ya que solo se usan en este método.
- Usa `self._unwrap_app_credentials()` directamente (eliminado el `getattr` check).
- Usa `self._token_request()` para el intercambio del código de autorización.
- Usa `self._wrap_account_tokens()` directamente (eliminado el `getattr` check).
- Extrae credenciales (client_id, client_secret, tenant, redirect_uri, scopes) del dict de `app_credentials`.
- Mantiene la lógica PKCE y servidor local intacta.
- Asigna `self._access_token` tras obtener tokens.
- Return type: `dict[str, Any]` (siempre retorna tokens, igual que Gmail).

**`authenticate_silent(app_credentials, user_tokens)`** — Implementado:
1. Unwrap credentials y tokens con helpers.
2. Validar access_token presente → `EmailMissingTokenError`.
3. Parsear expiry con `_parse_expiry`.
4. Si no expirado → `self._access_token = access_token`, return `None`.
5. Si expirado y sin refresh_token → `EmailMissingRefreshTokenError`.
6. Si expirado con refresh_token → POST al token endpoint con `grant_type=refresh_token`.
7. **Diferencia clave con Gmail**: Microsoft puede devolver un nuevo refresh_token (rotating tokens). Se persiste siempre el nuevo refresh_token si viene en la respuesta; si no, se mantiene el anterior.
8. `self._access_token = new_access_token`.
9. Retorna wrapped `token_record` con access_token, refresh_token, expiry, scopes.
10. En caso de error HTTP del token endpoint → `EmailRefreshFailedError`.

**`fetch_unread_emails(max_total=200, page_size=50)`** — Implementado:
1. Verificar `self._access_token` → `EmailNotAuthenticatedError`.
2. Query a Graph API: `GET /me/messages?$filter=isRead eq false&$top={page_size}&$select=id,conversationId,subject,from,toRecipients,bodyPreview,receivedDateTime,isRead&$orderby=receivedDateTime desc`.
3. Paginación con `@odata.nextLink` hasta alcanzar `max_total`.
4. Normalizar cada mensaje a `EmailMessage`:
   - `message_id` = `msg["id"]`
   - `thread_id` = `msg["conversationId"]`
   - `subject` = `msg["subject"]`
   - `sender` = formateado desde `msg["from"]["emailAddress"]` → `"Name <address>"`
   - `recipients` = extraídos de `msg["toRecipients"]`
   - `body` = `msg["bodyPreview"]`
   - `sent_at` = parseado de `msg["receivedDateTime"]` (ISO 8601 con Z)
   - `is_unread` = `True`
   - `provider` = `"outlook"`

**`send_email(subject, body, recipients)`** — Implementado:
1. Verificar `self._access_token` → `EmailNotAuthenticatedError`.
2. Verificar recipients → `EmailRecipientsMissingError`.
3. Construir payload para Graph API:
   ```python
   {"message": {
       "subject": subject,
       "body": {"contentType": "Text", "content": body},
       "toRecipients": [{"emailAddress": {"address": r}} for r in recipients]
   }}
   ```
4. POST a `{GRAPH_BASE_URL}/me/sendMail`.

---

## Paso 8 — Actualizar `CLAUDE.md`

Cambios documentados en `CLAUDE.md`:
- Outlook ahora está completamente soportado (eliminado "partial").
- Nueva variable de entorno: `MIA_OUTLOOK_CREDENTIALS_PATH`.
- Variable de tokens renombrada a `MIA_TOKEN_PATH` (compartida por ambos proveedores).
- `ProviderNotSupported` eliminado de la jerarquía de errores; proveedores desconocidos usan `AccountMisconfigured` / `EmailProviderConfigError`.
- Constructor de `OutlookClient` simplificado (solo `account_label`).
- `token_store`, `services_helpers`, `accounts_service`, `emails_service` son ahora provider-aware.
- Funciones de load/save tokens reciben `provider` como parámetro.
- Referencia a `CLIENT_GUIDE.md` como guía de extensibilidad.

---

## Paso 9 — Crear `CLIENT_GUIDE.md`

### `backend/core/email/CLIENT_GUIDE.md`

Documento que sirve como guía y plantilla para implementar nuevos clientes. Contenido:
1. Anatomía de un `EmailClient` (contrato abstracto con sus 5 métodos).
2. Estructura del constructor (`account_label`, estado del cliente API).
3. Flujo de `authenticate` (interactivo, OAuth2, retorna wrapped tokens).
4. Flujo de `authenticate_silent` (no-interactivo, refresh tokens, retorna tokens actualizados o `None`).
5. Flujo de `fetch_unread_emails` (paginación, normalización a `EmailMessage`).
6. Flujo de `send_email` (validación, construcción de payload, envío).
7. Helpers comunes (`_unwrap_app_credentials`, `_unwrap_user_tokens`, `_wrap_account_tokens`, `_parse_expiry`).
8. Qué cambiar fuera del cliente (`token_store`, `services_helpers`, `email_manager._build_client`, `CLAUDE.md`).
9. Comparativa Gmail vs Outlook como referencia.
10. Checklist de implementación para nuevos proveedores.

---

## Paso 10 — Adaptar `generalTest.py`

### `backend/tests/generalTest.py`
- Añadir creación de una cuenta Outlook (`provider: "outlook"`, `display_label: "outlook_test"`).
- Resolver su `account_id` junto con los de Gmail.
- Añadir paso de connect para la cuenta Outlook (flujo OAuth interactivo).
- El flujo de fetch unread y send se ejecuta a nivel de mailbox, por lo que automáticamente incluye la cuenta Outlook conectada.

---

## Resumen de archivos modificados

| Archivo | Acción |
|---|---|
| `backend/core/email/errors.py` | Eliminar `EmailProviderNotSupportedError` |
| `backend/core/email/outlook_client.py` | Reescritura completa |
| `backend/core/email/email_manager.py` | Simplificar `_build_client`, cambiar error fallback |
| `backend/api/errors/exceptions.py` | Eliminar `ProviderNotSupported` |
| `backend/api/errors/__init__.py` | Eliminar `ProviderNotSupported` del export |
| `backend/api/errors/handlers.py` | Eliminar `ProviderNotSupported` del mapa e imports |
| `backend/api/storage/token_store.py` | Provider-aware en todas las funciones, `MIA_TOKEN_PATH` |
| `backend/api/services/services_helpers.py` | Provider-aware en load functions, eliminar mapping obsoleto |
| `backend/api/services/accounts_service.py` | Pasar provider a credential/token loading |
| `backend/api/services/emails_service.py` | Per-account provider handling, label_lookup con provider |
| `backend/tests/generalTest.py` | Añadir flujo de cuenta Outlook |
| `CLAUDE.md` | Actualizar documentación |
| `backend/core/email/CLIENT_GUIDE.md` | **Nuevo** — guía de implementación de clientes |

---

## Verificación

1. **Arranque del servidor**: `python backend/main.py` — verificar que arranca sin errores de import.
2. **Revisar imports**: Asegurar que ningún archivo importe `ProviderNotSupported` o `EmailProviderNotSupportedError` tras eliminarlos.
3. **Test manual de flujo connect**: Verificar que `POST /mailboxes/{id}/accounts/{id}/connect` funciona para ambos proveedores.
4. **Test manual de fetch/send**: Verificar que el flujo completo de fetch unread y send email funciona con una cuenta Outlook real.
5. **Ejecución del generalTest**: `python backend/tests/generalTest.py` — flujo completo incluyendo Gmail y Outlook.
