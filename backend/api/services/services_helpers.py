"""
Shared helpers used across service modules.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Iterable

logger = logging.getLogger(__name__)

import bleach
from pydantic import SecretStr

from auth import (
    AuthError,
    AuthSettingsError,
    AuthTokenError,
    AuthTokenInvalidError,
    AuthTokenNetworkError,
    AuthTokenProviderError,
)
from core.email import (
    CoreError,
    EmailAccountNotFoundError,
    EmailAccountRecordError,
    EmailAuthError,
    EmailConfigError,
    EmailDuplicateAccountLabelError,
    EmailExternalAPIError,
    EmailInvalidCredentialsDataError,
    EmailInvalidExpiryError,
    EmailInvalidTokenDataError,
    EmailManager,
    EmailMetadata,
    EmailMissingAppCredentialsError,
    EmailMissingRefreshTokenError,
    EmailMissingTokenError,
    EmailNotAuthenticatedError,
    EmailProviderConfigError,
    EmailRecipientsMissingError,
    EmailRefreshFailedError,
    LabelUpdate,
    SpamMoveResult,
)

from api.errors.exceptions import (
    AccountConnectAuthError,
    AccountMisconfigured,
    AccountNotConnected,
    AccountNotFound,
    ApiError,
    AppCredentialsInvalid,
    AppCredentialsMissing,
    CredentialFileError,
    DatabaseConnectionError,
    DatabaseMigrationError,
    DatabaseQueryError,
    EnvVarError,
    ExternalAPIError,
    Forbidden,
    MailboxNotFound,
    RecipientsMissing,
    TokenDecryptionError,
    TokenEncryptionError,
    TokenIntegrityError,
    Unauthorized,
)
from database import (
    account_store,
    email_content_store,
    ConnectionPoolError,
    CredentialReadError,
    DatabaseError,
    email_metadata_store,
    load_app_credentials,
    mailbox_store,
    MigrationError,
    QueryError,
    SettingsError,
    TokenCryptoError,
    TokenDecryptError,
    TokenEncryptError,
    TokenValidationError,
    UnknownProviderError,
)


# ---------------------------------------------------------------------------
# Core → API error mapping (most specific first; evaluated with isinstance)
# ---------------------------------------------------------------------------

_CORE_TO_API_MAP: list[tuple[type[CoreError], type[ApiError]]] = [
    (EmailAccountNotFoundError, AccountNotFound),
    (EmailMissingTokenError, AccountNotConnected),
    (EmailMissingRefreshTokenError, AccountNotConnected),
    (EmailRefreshFailedError, AccountNotConnected),
    (EmailNotAuthenticatedError, AccountNotConnected),
    (EmailAuthError, AccountNotConnected),
    (EmailInvalidExpiryError, AccountMisconfigured),
    (EmailInvalidCredentialsDataError, AppCredentialsInvalid),
    (EmailInvalidTokenDataError, AccountMisconfigured),
    (EmailAccountRecordError, AccountMisconfigured),
    (EmailProviderConfigError, AccountMisconfigured),
    (EmailMissingAppCredentialsError, AppCredentialsMissing),
    (EmailDuplicateAccountLabelError, AccountMisconfigured),
    (EmailConfigError, AccountMisconfigured),
    (EmailRecipientsMissingError, RecipientsMissing),
    (EmailExternalAPIError, ExternalAPIError),
    (CoreError, ApiError),
]


# ---------------------------------------------------------------------------
# Database → API error mapping (most specific first; evaluated with isinstance)
# ---------------------------------------------------------------------------

_DB_TO_API_MAP: list[tuple[type[DatabaseError], type[ApiError]]] = [
    (ConnectionPoolError, DatabaseConnectionError),
    (QueryError, DatabaseQueryError),
    (MigrationError, DatabaseMigrationError),
    (SettingsError, EnvVarError),
    (TokenDecryptError, TokenDecryptionError),
    (TokenEncryptError, TokenEncryptionError),
    (TokenCryptoError, TokenDecryptionError),
    (TokenValidationError, TokenIntegrityError),
    (CredentialReadError, CredentialFileError),
    (UnknownProviderError, AccountMisconfigured),
    (DatabaseError, ApiError),
]


# ---------------------------------------------------------------------------
# Auth → API error mapping (most specific first; evaluated with isinstance)
# ---------------------------------------------------------------------------

_AUTH_TO_API_MAP: list[tuple[type[AuthError], type[ApiError]]] = [
    (AuthSettingsError, EnvVarError),
    (AuthTokenNetworkError, ExternalAPIError),
    (AuthTokenInvalidError, Unauthorized),
    (AuthTokenProviderError, Unauthorized),
    (AuthTokenError, Unauthorized),
    (AuthError, ApiError),
]


def translate_auth_error(
    exc: Exception,
    *,
    fallback: type[ApiError] = ApiError,
    context: dict[str, Any] | None = None,
) -> ApiError:
    """
    Translate an AuthError into the corresponding ApiError using the mapping.

    If *exc* is an AuthError subclass the first matching entry in
    ``_AUTH_TO_API_MAP`` is used.  Otherwise *fallback* is instantiated.
    """
    if isinstance(exc, AuthError):
        for auth_type, api_type in _AUTH_TO_API_MAP:
            if isinstance(exc, auth_type):
                detail = exc.detail if hasattr(exc, "detail") else {}
                if context:
                    detail = {**detail, **context}
                detail["auth_code"] = exc.code
                return api_type(exc.message, detail)
        # Unreachable when AuthError is in the map, but safe fallback.
        return fallback(str(exc), {**(context or {}), "auth_code": exc.code})
    return fallback(str(exc) or "Unexpected auth error.", context or {})


def translate_core_error(
    exc: Exception,
    *,
    fallback: type[ApiError] = ApiError,
    context: dict[str, Any] | None = None,
) -> ApiError:
    """
    Translate a CoreError into the corresponding ApiError using the mapping.

    If *exc* is a CoreError subclass the first matching entry in
    ``_CORE_TO_API_MAP`` is used.  Otherwise *fallback* is instantiated.
    """
    if isinstance(exc, CoreError):
        for core_type, api_type in _CORE_TO_API_MAP:
            if isinstance(exc, core_type):
                detail = exc.detail if hasattr(exc, "detail") else {}
                if context:
                    detail = {**detail, **context}
                detail["core_code"] = exc.code
                return api_type(exc.message, detail)
        # Unreachable when CoreError is in the map, but safe fallback.
        return fallback(str(exc), {**(context or {}), "core_code": exc.code})
    return fallback(str(exc) or "Unexpected error.", context or {})


def translate_database_error(
    exc: Exception,
    *,
    fallback: type[ApiError] = ApiError,
    context: dict[str, Any] | None = None,
) -> ApiError:
    """
    Translate a DatabaseError into the corresponding ApiError using the mapping.

    If *exc* is a DatabaseError subclass the first matching entry in
    ``_DB_TO_API_MAP`` is used.  Otherwise *fallback* is instantiated.
    """
    if isinstance(exc, DatabaseError):
        for db_type, api_type in _DB_TO_API_MAP:
            if isinstance(exc, db_type):
                detail = exc.detail if hasattr(exc, "detail") else {}
                if context:
                    detail = {**detail, **context}
                detail["db_code"] = exc.code
                return api_type(exc.message, detail)
        # Unreachable when DatabaseError is in the map, but safe fallback.
        return fallback(str(exc), {**(context or {}), "db_code": exc.code})
    return fallback(str(exc) or "Unexpected database error.", context or {})



def translate_connect_error(
    exc: Exception,
    *,
    context: dict[str, Any] | None = None,
) -> ApiError:
    """
    Translate errors for the interactive account-connect flow.

    Unlike mailbox operations that require a pre-connected account (409),
    connect-time authentication failures should return 401.
    """
    if isinstance(exc, EmailAuthError):
        detail = exc.detail if hasattr(exc, "detail") else {}
        if context:
            detail = {**detail, **context}
        detail["core_code"] = exc.code
        return AccountConnectAuthError(exc.message, detail)
    return translate_core_error(exc, fallback=AccountConnectAuthError, context=context)


def ensure_mailbox_access(mailbox_id: str, user_id: str) -> dict[str, Any]:
    """
    Ensure the mailbox exists and the authenticated user owns it.

    Returns the mailbox record so callers can reuse it without a second fetch.
    """
    try:
        record = mailbox_store.get(mailbox_id)
    except DatabaseError as exc:
        raise translate_database_error(exc) from exc
    except Exception as exc:
        logger.warning("Unexpected mailbox lookup error (%s): %s", type(exc).__name__, exc)
        raise ApiError("Failed to look up mailbox.") from exc
    if record is None:
        raise MailboxNotFound(f"Mailbox '{mailbox_id}' not found.")
    if record.get("owner_user_id") != user_id:
        raise Forbidden("You do not have access to this mailbox.")
    return record


def build_manager_for_accounts(accounts: Iterable[dict[str, Any]]) -> EmailManager:
    """
    Build an EmailManager and register all account records on it.
    """
    manager = EmailManager()
    for account in accounts:
        try:
            manager.add_account_record(account)
        except CoreError as exc:
            raise translate_core_error(exc, fallback=AccountMisconfigured) from exc
        except Exception as exc:
            logger.warning("Failed to register account in manager (%s): %s", type(exc).__name__, exc)
            raise AccountMisconfigured(
                "Failed to register account in manager."
            ) from exc
    return manager


def raise_on_silent_auth_errors(
    errors: dict[str, Exception],
    *,
    fallback: type[ApiError] = ApiError,
) -> None:
    """
    Inspect the per-account errors collected during EmailManager.authenticate_all_silent().

    - Non-auth CoreErrors are translated via the centralized mapping and raised immediately.
    - Auth-related errors are accumulated and raised as a single AccountNotConnected.
    - Non-CoreError exceptions are raised through the fallback path.
    """
    if not errors:
        return

    auth_labels: list[str] = []
    reasons: dict[str, str] = {}
    for label, error in errors.items():
        if is_auth_error(error):
            auth_labels.append(label)
            reason = str(error).strip()
            if reason:
                reasons[label] = reason
        else:
            raise translate_core_error(error, fallback=fallback) from error

    if auth_labels:
        detail: dict[str, Any] = {"account_labels": auth_labels}
        if reasons:
            detail["reasons"] = reasons
        raise AccountNotConnected(
            "One or more accounts are not connected. Call /connect first.",
            detail,
        )


def is_auth_error(exc: Exception) -> bool:
    """
    Return True when the exception is a typed core authentication error.
    """
    return isinstance(exc, EmailAuthError)


def _wrap_secret(value: Any) -> Any:
    if value is None:
        return None
    return SecretStr(str(value))


def unwrap_secret(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, SecretStr):
        return value.get_secret_value()
    return value


def load_wrapped_app_credentials(provider: str) -> dict[str, Any]:
    """
    Load app credentials for *provider* and wrap the client_secret as SecretStr.
    """
    try:
        credentials = load_app_credentials(provider)
    except DatabaseError as exc:
        raise translate_database_error(exc) from exc
    except Exception as exc:
        logger.warning("Unexpected credentials load error (%s): %s", type(exc).__name__, exc)
        raise ApiError("Failed to load app credentials.") from exc
    payload = dict(credentials) if isinstance(credentials, dict) else {}
    if "client_secret" in payload:
        payload["client_secret"] = _wrap_secret(payload.get("client_secret"))
    return payload


def load_wrapped_account_tokens(
    mailbox_id: str, account_id: str, provider: str,
) -> dict[str, Any]:
    """
    Load account tokens for *provider* and wrap access/refresh tokens as SecretStr.
    """
    try:
        token_data = account_store.get_tokens(mailbox_id, account_id, provider)
    except DatabaseError as exc:
        raise translate_database_error(exc) from exc
    except Exception as exc:
        logger.warning("Unexpected token load error (%s): %s", type(exc).__name__, exc)
        raise ApiError("Failed to load account tokens.") from exc
    payload = dict(token_data) if isinstance(token_data, dict) else {}
    if "access_token" in payload:
        payload["access_token"] = _wrap_secret(payload.get("access_token"))
    if "refresh_token" in payload:
        payload["refresh_token"] = _wrap_secret(payload.get("refresh_token"))
    return payload


# ---------------------------------------------------------------------------
# Email metadata persistence helpers
# ---------------------------------------------------------------------------


def persist_email_metadata_batch(
    account_id: str,
    metadata_list: list[EmailMetadata],
    *,
    fallback: type[ApiError] = ApiError,
) -> int:
    """Persist email metadata to DB via batch upsert. Returns rows affected."""
    if not metadata_list:
        return 0
    rows = [
        (
            m.provider_message_id, account_id, m.thread_id, m.from_email,
            m.from_name, m.subject, m.received_at, m.is_read, m.box,
        )
        for m in metadata_list
    ]
    try:
        return email_metadata_store.upsert_batch(account_id, rows)
    except DatabaseError as exc:
        raise translate_database_error(exc) from exc
    except Exception as exc:
        logger.warning("Unexpected metadata persist error (%s): %s", type(exc).__name__, exc)
        raise fallback("Failed to persist email metadata.") from exc


def load_sync_cursors(
    label_lookup: dict[str, tuple[str, str, str]],
    *,
    fallback: type[ApiError] = ApiError,
) -> dict[str, str | None]:
    """Load the sync cursor for each account, keyed by account label."""
    cursors: dict[str, str | None] = {}
    for label, (mailbox_id, account_id, _provider) in label_lookup.items():
        try:
            cursors[label] = account_store.get_sync_cursor(mailbox_id, account_id)
        except DatabaseError as exc:
            raise translate_database_error(exc) from exc
        except Exception as exc:
            logger.warning("Unexpected sync cursor load error (%s): %s", type(exc).__name__, exc)
            raise fallback("Failed to load sync cursor.") from exc
    return cursors


def delete_email_metadata_batch(
    account_id: str,
    message_ids: list[str],
    *,
    fallback: type[ApiError] = ApiError,
) -> int:
    """Delete email metadata by provider_message_ids. Returns rows deleted."""
    if not message_ids:
        return 0
    try:
        return email_metadata_store.delete_batch_by_message_ids(account_id, message_ids)
    except DatabaseError as exc:
        raise translate_database_error(exc) from exc
    except Exception as exc:
        logger.warning("Unexpected metadata delete error (%s): %s", type(exc).__name__, exc)
        raise fallback("Failed to delete email metadata.") from exc


def update_email_metadata_labels_batch(
    account_id: str,
    label_updates: list[LabelUpdate],
    *,
    fallback: type[ApiError] = ApiError,
) -> int:
    """Update only is_read and box for specific messages. Returns rows updated."""
    if not label_updates:
        return 0
    rows = [
        (lu.provider_message_id, account_id, lu.is_read, lu.box)
        for lu in label_updates
    ]
    try:
        return email_metadata_store.update_labels_batch(account_id, rows)
    except DatabaseError as exc:
        raise translate_database_error(exc) from exc
    except Exception as exc:
        logger.warning("Unexpected metadata labels update error (%s): %s", type(exc).__name__, exc)
        raise fallback("Failed to update email metadata labels.") from exc


def update_email_read_status_batch(
    account_id: str,
    message_ids: list[str],
    is_read: bool,
    *,
    fallback: type[ApiError] = ApiError,
) -> int:
    """Update only is_read for specific messages. Returns rows updated."""
    if not message_ids:
        return 0
    rows = [(mid, account_id, is_read) for mid in message_ids]
    try:
        return email_metadata_store.update_read_status_batch(account_id, rows)
    except DatabaseError as exc:
        raise translate_database_error(exc) from exc
    except Exception as exc:
        logger.warning(
            "Unexpected read status DB update error (%s): %s",
            type(exc).__name__, exc,
        )
        raise fallback("Failed to update email read status in database.") from exc


def update_email_spam_status_batch(
    account_id: str,
    results: list[SpamMoveResult],
    new_box: str,
    *,
    fallback: type[ApiError] = ApiError,
) -> int:
    """Update provider_message_id and box for messages moved to/from spam. Returns rows updated."""
    if not results:
        return 0
    rows = [
        (r.old_id, account_id, r.new_id, new_box)
        for r in results
    ]
    try:
        return email_metadata_store.update_spam_status_batch(account_id, rows)
    except DatabaseError as exc:
        raise translate_database_error(exc) from exc
    except Exception as exc:
        logger.warning(
            "Unexpected spam status DB update error (%s): %s",
            type(exc).__name__, exc,
        )
        raise fallback("Failed to update email spam status in database.") from exc


def load_stored_message_ids(
    account_id: str,
    *,
    fallback: type[ApiError] = ApiError,
) -> list[str]:
    """Load all provider_message_ids stored for an account."""
    try:
        return email_metadata_store.list_provider_message_ids(account_id)
    except DatabaseError as exc:
        raise translate_database_error(exc) from exc
    except Exception as exc:
        logger.warning("Unexpected stored message IDs load error (%s): %s", type(exc).__name__, exc)
        raise fallback("Failed to load stored message IDs.") from exc


def get_trash_emails_by_ids(
    account_id: str,
    message_ids: list[str],
    *,
    fallback: type[ApiError] = ApiError,
) -> list[dict[str, Any]]:
    """Get emails in TRASH by their provider_message_ids."""
    if not message_ids:
        return []
    try:
        return email_metadata_store.get_trash_emails_by_ids(account_id, message_ids)
    except DatabaseError as exc:
        raise translate_database_error(exc) from exc
    except Exception as exc:
        logger.warning("Unexpected get trash emails error (%s): %s", type(exc).__name__, exc)
        raise fallback("Failed to get trash emails.") from exc


def mark_as_deleted_batch(
    account_id: str,
    message_ids: list[str],
    *,
    fallback: type[ApiError] = ApiError,
) -> int:
    """Mark emails as DELETED in the database."""
    if not message_ids:
        return 0
    try:
        return email_metadata_store.mark_as_deleted_batch(account_id, message_ids)
    except DatabaseError as exc:
        raise translate_database_error(exc) from exc
    except Exception as exc:
        logger.warning("Unexpected mark as deleted error (%s): %s", type(exc).__name__, exc)
        raise fallback("Failed to mark emails as deleted.") from exc


def restore_from_trash_batch(
    account_id: str,
    rows: list[tuple],
    *,
    fallback: type[ApiError] = ApiError,
) -> int:
    """Restore emails from trash in the database."""
    if not rows:
        return 0
    try:
        return email_metadata_store.restore_from_trash_batch(account_id, rows)
    except DatabaseError as exc:
        raise translate_database_error(exc) from exc
    except Exception as exc:
        logger.warning("Unexpected restore from trash error (%s): %s", type(exc).__name__, exc)
        raise fallback("Failed to restore emails from trash.") from exc


def restore_from_trash_discovered_batch(
    account_id: str,
    rows: list[tuple],
    *,
    fallback: type[ApiError] = ApiError,
) -> int:
    """Restore emails from trash with a discovered box in the database."""
    if not rows:
        return 0
    try:
        return email_metadata_store.restore_from_trash_discovered_batch(account_id, rows)
    except DatabaseError as exc:
        raise translate_database_error(exc) from exc
    except Exception as exc:
        logger.warning("Unexpected restore discovered box error (%s): %s", type(exc).__name__, exc)
        raise fallback("Failed to restore emails with discovered box.") from exc


def move_to_trash_batch(
    account_id: str,
    rows: list[tuple],
    *,
    fallback: type[ApiError] = ApiError,
) -> int:
    """Move emails to trash in the database."""
    if not rows:
        return 0
    try:
        return email_metadata_store.move_to_trash_batch(account_id, rows)
    except DatabaseError as exc:
        raise translate_database_error(exc) from exc
    except Exception as exc:
        logger.warning("Unexpected move to trash error (%s): %s", type(exc).__name__, exc)
        raise fallback("Failed to move emails to trash.") from exc


def update_sync_cursor(
    mailbox_id: str,
    account_id: str,
    cursor: str,
    *,
    fallback: type[ApiError] = ApiError,
) -> None:
    """Persist the new sync_cursor for an account."""
    try:
        account_store.update_sync_cursor(mailbox_id, account_id, cursor)
    except DatabaseError as exc:
        raise translate_database_error(exc) from exc
    except Exception as exc:
        logger.warning("Unexpected sync cursor update error (%s): %s", type(exc).__name__, exc)
        raise fallback("Failed to update sync cursor.") from exc


# ---------------------------------------------------------------------------
# Email content helpers
# ---------------------------------------------------------------------------

_SANITIZE_ALLOWED_TAGS = [
    "a", "abbr", "b", "blockquote", "br", "center", "code", "dd", "del",
    "div", "dl", "dt", "em", "font", "h1", "h2", "h3", "h4", "h5", "h6",
    "hr", "i", "img", "ins", "li", "mark", "ol", "p", "pre", "q", "s",
    "small", "span", "strong", "sub", "sup", "table", "tbody", "td",
    "tfoot", "th", "thead", "tr", "u", "ul", "wbr",
]

_SANITIZE_ALLOWED_ATTRIBUTES = {
    "*": ["class", "id", "style", "dir", "lang", "title", "align", "valign"],
    "a": ["href", "target", "rel"],
    "img": ["src", "alt", "width", "height", "border"],
    "td": ["colspan", "rowspan", "width", "height", "align", "valign", "bgcolor"],
    "th": ["colspan", "rowspan", "width", "height", "align", "valign", "bgcolor"],
    "table": ["border", "cellpadding", "cellspacing", "width", "align", "bgcolor"],
    "font": ["color", "size", "face"],
    "ol": ["start", "type"],
}

_SANITIZE_ALLOWED_PROTOCOLS = ["http", "https", "mailto", "cid", "data"]

# Raw-text HTML elements whose contents must be stripped together with their
# tags. bleach's ``strip=True`` only removes the tags of disallowed elements
# but preserves their text contents, which is unsafe for <script> and <style>
# because the inner text is executable/interpreted by the browser. We remove
# these blocks with a regex before handing the HTML to bleach. The alternation
# ``</\1\s*>|\Z`` also matches unterminated blocks that extend to EOF, so a
# malformed ``<script>alert(1)`` without a closing tag is still removed.
_RAW_TEXT_BLOCK_PATTERN = re.compile(
    r"<(script|style)\b[^>]*>.*?(?:</\1\s*>|\Z)",
    re.DOTALL | re.IGNORECASE,
)

# Outlook wraps its desktop-optimized layout in MSO/IE conditional comments
# (``<!--[if mso | IE]>…<![endif]-->``). Bleach's default ``strip_comments=True``
# removes them wholesale, taking the real desktop layout with them and leaving
# only the non-MSO mobile fallback (placeholders like ``<table width="4%">``
# that collapse to a few pixels). We unwrap the *content* of these conditionals
# before bleach so the desktop layout survives and gets sanitized normally.
# The pattern also matches the ``[if !mso]><!-- … --><![endif]`` variant used
# for non-MSO fallbacks; unwrapping both is safe (the surrounding comment
# boundaries are what bleach was going to strip).
_MSO_CONDITIONAL_PATTERN = re.compile(
    r"<!--\s*\[if[^\]]*\]>(.*?)<!\[endif\]-->",
    re.DOTALL | re.IGNORECASE,
)

# CSS properties safe to preserve inside ``style="..."`` attributes. The list
# covers the vocabulary actually used by real email templates (layout, colors,
# typography, spacing, simple borders) without opening the door to properties
# that pull in remote resources or execute logic.
_SANITIZE_ALLOWED_CSS_PROPERTIES = frozenset({
    "align-items", "background", "background-color", "background-image",
    "background-position", "background-repeat", "background-size", "border",
    "border-bottom", "border-bottom-color", "border-bottom-left-radius",
    "border-bottom-right-radius", "border-bottom-style", "border-bottom-width",
    "border-collapse", "border-color", "border-left", "border-left-color",
    "border-left-style", "border-left-width", "border-radius", "border-right",
    "border-right-color", "border-right-style", "border-right-width",
    "border-spacing", "border-style", "border-top", "border-top-color",
    "border-top-left-radius", "border-top-right-radius", "border-top-style",
    "border-top-width", "border-width", "bottom", "box-shadow", "box-sizing",
    "caption-side", "clear", "color", "display", "empty-cells", "float",
    "font", "font-family", "font-size", "font-stretch", "font-style",
    "font-variant", "font-weight", "height", "justify-content", "left",
    "letter-spacing", "line-height", "list-style", "list-style-position",
    "list-style-type", "margin", "margin-bottom", "margin-left", "margin-right",
    "margin-top", "max-height", "max-width", "min-height", "min-width",
    "mso-line-height-rule", "mso-table-lspace", "mso-table-rspace", "opacity",
    "outline", "overflow", "overflow-wrap", "overflow-x", "overflow-y",
    "padding", "padding-bottom", "padding-left", "padding-right", "padding-top",
    "page-break-after", "page-break-before", "position", "right",
    "table-layout", "text-align", "text-decoration", "text-indent",
    "text-overflow", "text-shadow", "text-transform", "top", "vertical-align",
    "visibility", "white-space", "width", "word-break", "word-spacing",
    "word-wrap", "z-index",
})

_SANITIZE_ALLOWED_CSS_SVG_PROPERTIES = frozenset()


def sanitize_email_html(html: str) -> str:
    """Sanitize email HTML to remove dangerous tags, attributes and protocols.

    Inlines CSS rules from <style> blocks into element ``style`` attributes
    before the regex/bleach pass so the visual styling survives. Only
    inlinable rules are kept; @media / @font-face blocks are dropped with the
    residual <style> tag. If the inliner fails on malformed HTML, the content
    still goes through bleach (email renders flat but no 500).
    """
    if not html or html.isspace():
        return html
    # Unwrap MSO/IE conditional comments BEFORE premailer so lxml parses their
    # content as regular markup. Doing it after premailer is too late — lxml
    # discards conditional comment blocks when it serialises the tree back out.
    html = _MSO_CONDITIONAL_PATTERN.sub(lambda m: m.group(1), html)
    try:
        from premailer import transform  # lazy import — avoids startup cost
        html = transform(
            html,
            keep_style_tags=False,
            remove_classes=False,
            cssutils_logging_level="CRITICAL",
            disable_validation=True,
        )
    except Exception as exc:
        logger.warning("premailer failed (%s): %s", type(exc).__name__, exc)
    html = _RAW_TEXT_BLOCK_PATTERN.sub("", html)
    from bleach.css_sanitizer import CSSSanitizer  # lazy import — optional dep
    css_sanitizer = CSSSanitizer(
        allowed_css_properties=_SANITIZE_ALLOWED_CSS_PROPERTIES,
        allowed_svg_properties=_SANITIZE_ALLOWED_CSS_SVG_PROPERTIES,
    )
    return bleach.clean(
        html,
        tags=_SANITIZE_ALLOWED_TAGS,
        attributes=_SANITIZE_ALLOWED_ATTRIBUTES,
        protocols=_SANITIZE_ALLOWED_PROTOCOLS,
        css_sanitizer=css_sanitizer,
        strip=True,
    )


def get_email_content(
    account_id: str,
    provider_message_id: str,
    *,
    fallback: type[ApiError] = ApiError,
) -> dict[str, Any] | None:
    """Read cached email content from DB. Returns dict or None."""
    try:
        return email_content_store.get(account_id, provider_message_id)
    except DatabaseError as exc:
        raise translate_database_error(exc) from exc
    except Exception as exc:
        logger.warning("Unexpected email content read error (%s): %s", type(exc).__name__, exc)
        raise fallback("Failed to read email content from database.") from exc


def persist_email_content(
    account_id: str,
    provider_message_id: str,
    html_body: str | None,
    text_body: str | None,
    *,
    fallback: type[ApiError] = ApiError,
) -> None:
    """Persist email content to DB. CAN raise — caller decides best-effort wrapping."""
    try:
        email_content_store.upsert(account_id, provider_message_id, html_body, text_body)
    except DatabaseError as exc:
        raise translate_database_error(exc) from exc
    except Exception as exc:
        logger.warning("Unexpected email content persist error (%s): %s", type(exc).__name__, exc)
        raise fallback("Failed to persist email content.") from exc
