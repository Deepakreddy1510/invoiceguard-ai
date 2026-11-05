"""Small bounded Google OAuth/Gmail client. URLs never come from email content."""

import base64
import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from urllib.parse import urlencode, urlsplit

import httpx
from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings

SCOPE = "https://www.googleapis.com/auth/gmail.readonly"


class GoogleFailure(RuntimeError):
    def __init__(
        self,
        message="Gmail is temporarily unavailable. Retry is scheduled.",
        auth=False,
        status=0,
        retry_after=0,
    ):
        super().__init__(message)
        self.auth, self.status, self.retry_after = auth, status, retry_after


def now():
    return datetime.now(timezone.utc)


def configured():
    s = get_settings()
    try:
        origin, redirect = urlsplit(s.gmail_trusted_origin), urlsplit(s.gmail_redirect_uri)
        if not (s.gmail_client_id and s.gmail_client_secret and s.gmail_encryption_key):
            return False
        Fernet(s.gmail_encryption_key.get_secret_value().encode())
        return (
            (origin.scheme, origin.netloc) == (redirect.scheme, redirect.netloc)
            and bool(origin.netloc)
            and not origin.username
            and not origin.password
            and origin.path in ("", "/")
            and not origin.query
            and not origin.fragment
            and redirect.path == "/api/v1/email/oauth/callback"
            and not redirect.query
            and not redirect.fragment
            and (
                origin.scheme == "https"
                or (
                    s.app_environment == "local"
                    and origin.scheme == "http"
                    and origin.hostname in ("localhost", "127.0.0.1")
                )
            )
        )
    except (ValueError, TypeError):
        return False


def seal(workspace_id, data):
    key = get_settings().gmail_encryption_key
    if not key:
        raise GoogleFailure("Gmail encryption is not configured.", auth=True)
    return (
        Fernet(key.get_secret_value().encode())
        .encrypt(json.dumps({"workspace_id": str(workspace_id), "data": data}).encode())
        .decode()
    )


def unseal(workspace_id, ciphertext):
    try:
        payload = json.loads(
            Fernet(get_settings().gmail_encryption_key.get_secret_value().encode()).decrypt(
                ciphertext.encode()
            )
        )
        if payload["workspace_id"] != str(workspace_id):
            raise ValueError("Workspace binding")
        return payload["data"]
    except (InvalidToken, ValueError, KeyError, AttributeError, TypeError):
        raise GoogleFailure(
            "Gmail credentials cannot be decrypted. Reconnect with the configured encryption key.",
            auth=True,
        ) from None


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def authorization_url(state, verifier):
    s = get_settings()
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(
        {
            "client_id": s.gmail_client_id,
            "redirect_uri": s.gmail_redirect_uri,
            "response_type": "code",
            "scope": SCOPE,
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )


class PrivateGoogleTransportLog(logging.Filter):
    def filter(self, record):
        # httpx INFO lines include resource IDs in URLs; keep mailbox IDs out of logs.
        return not any(
            host in record.getMessage()
            for host in ("gmail.googleapis.com", "oauth2.googleapis.com")
        )


class GmailClient:
    def __init__(self, access_token=None, client=None):
        logger = logging.getLogger("httpx")
        if not any(isinstance(item, PrivateGoogleTransportLog) for item in logger.filters):
            logger.addFilter(PrivateGoogleTransportLog())
        self.token = access_token
        self.client = client or httpx.Client(
            timeout=httpx.Timeout(20, connect=5), follow_redirects=False
        )
        self.owned = client is None

    def close(self):
        if self.owned:
            self.client.close()

    def request(self, method, url, *, limit=2_000_000, oauth=False, **kwargs):
        headers = {} if oauth else {"Authorization": "Bearer " + (self.token or "")}
        try:
            with self.client.stream(method, url, headers=headers, **kwargs) as response:
                if response.status_code >= 400:
                    raw_retry = response.headers.get("Retry-After", "0")
                    retry = min(int(raw_retry), 3600) if raw_retry.isdigit() else 0
                    quota = False
                    if response.status_code == 403:
                        error_bytes = bytearray()
                        for chunk in response.iter_bytes():
                            error_bytes.extend(chunk)
                            if len(error_bytes) > 16384:
                                break
                        try:
                            error = json.loads(error_bytes).get("error", {})
                            reasons = {entry.get("reason") for entry in error.get("errors", [])}
                            quota = (
                                bool(
                                    reasons
                                    & {
                                        "rateLimitExceeded",
                                        "userRateLimitExceeded",
                                        "dailyLimitExceeded",
                                        "quotaExceeded",
                                    }
                                )
                                or error.get("status") == "RESOURCE_EXHAUSTED"
                            )
                        except (ValueError, TypeError, AttributeError):
                            pass
                    authorization_error = response.status_code == 401 or (
                        response.status_code == 403 and not quota
                    )
                    raise GoogleFailure(
                        "Gmail authorization expired or access was denied. Reconnect the account."
                        if authorization_error
                        else "Gmail quota limit reached. Retry is scheduled."
                        if quota
                        else "Gmail request failed. Retry is scheduled.",
                        auth=authorization_error,
                        status=429 if quota else response.status_code,
                        retry_after=retry,
                    )
                if response.is_redirect:
                    raise GoogleFailure("Unexpected Gmail redirect was refused.")
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > limit:
                        raise GoogleFailure(
                            "Gmail response exceeds the intake size limit.", status=413
                        )
                return json.loads(body) if body else {}
        except (httpx.HTTPError, ValueError, TypeError):
            raise GoogleFailure() from None

    def exchange(self, code, verifier):
        s = get_settings()
        try:
            return self.request(
                "POST",
                "https://oauth2.googleapis.com/token",
                oauth=True,
                data={
                    "client_id": s.gmail_client_id,
                    "client_secret": s.gmail_client_secret.get_secret_value(),
                    "code": code,
                    "code_verifier": verifier,
                    "redirect_uri": s.gmail_redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
        except GoogleFailure as exc:
            raise GoogleFailure(
                "Google authorization could not be completed. Start Connect Gmail again.", auth=True
            ) from exc

    def refresh(self, refresh_token):
        s = get_settings()
        try:
            return self.request(
                "POST",
                "https://oauth2.googleapis.com/token",
                oauth=True,
                data={
                    "client_id": s.gmail_client_id,
                    "client_secret": s.gmail_client_secret.get_secret_value(),
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                },
            )
        except GoogleFailure as exc:
            if exc.status == 400:
                raise GoogleFailure(
                    "Google authorization expired or was revoked. Reconnect the account.", auth=True
                ) from None
            raise

    def revoke(self, token):
        try:
            self.request(
                "POST", "https://oauth2.googleapis.com/revoke", oauth=True, data={"token": token}
            )
        except GoogleFailure as exc:
            if exc.status != 400:  # Already invalid/revoked also ends local access.
                raise

    def profile(self):
        return self.request("GET", "https://gmail.googleapis.com/gmail/v1/users/me/profile")

    def history(self, history_id, page_token=None):
        params = {
            "startHistoryId": history_id,
            "historyTypes": "messageAdded",
            "labelId": "INBOX",
            "maxResults": 10,
        }
        if page_token:
            params["pageToken"] = page_token
        return self.request(
            "GET", "https://gmail.googleapis.com/gmail/v1/users/me/history", params=params
        )

    def recent(self, since, page_token=None):
        params = {"q": f"in:inbox after:{int(since.timestamp())}", "maxResults": 10}
        if page_token:
            params["pageToken"] = page_token
        return self.request(
            "GET", "https://gmail.googleapis.com/gmail/v1/users/me/messages", params=params
        )

    def message(self, message_id):
        self.identifier(message_id)
        return self.request(
            "GET",
            f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}",
            params={"format": "full"},
        )

    def attachment(self, message_id, attachment_id):
        self.identifier(message_id)
        self.identifier(attachment_id)
        data = self.request(
            "GET",
            f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}/attachments/{attachment_id}",
            limit=14_100_000,
        )
        return decode(data.get("data", ""), 10 * 1024 * 1024)

    @staticmethod
    def identifier(value):
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,1000}", value):
            raise GoogleFailure("Gmail returned an invalid resource identifier.")


def decode(value, limit):
    if not isinstance(value, str) or len(value) > limit * 4 // 3 + 8:
        raise GoogleFailure("Gmail part exceeds its allowed size.", status=413)
    try:
        data = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
    except (ValueError, TypeError):
        raise GoogleFailure("Gmail returned a malformed MIME part.", status=422) from None
    if len(data) > limit:
        raise GoogleFailure("Gmail part exceeds its allowed size.", status=413)
    return data


def access(connection):
    tokens = unseal(connection.workspace_id, connection.credentials)
    client = GmailClient(tokens.get("access_token"))
    try:
        if float(tokens.get("expires_at", 0)) <= now().timestamp() + 30:
            renewed = client.refresh(tokens["refresh_token"])
            tokens.update(
                access_token=renewed["access_token"],
                expires_at=now().timestamp() + min(int(renewed.get("expires_in", 3600)), 3600),
            )
            if renewed.get("refresh_token"):
                tokens["refresh_token"] = renewed["refresh_token"]
            connection.credentials = seal(connection.workspace_id, tokens)
            client.token = tokens["access_token"]
        return client
    except (ValueError, KeyError, TypeError):
        client.close()
        raise GoogleFailure(
            "Google returned unusable credentials. Reconnect the account.", auth=True
        ) from None
    except Exception:
        client.close()
        raise
