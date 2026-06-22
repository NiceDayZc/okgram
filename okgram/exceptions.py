"""
The full exception hierarchy for the client

Maps the errors Instagram returns (via the `message` / `error_type` field in
the JSON or the HTTP status) into exceptions that are convenient to catch.
"""
from __future__ import annotations

from typing import Optional


class ClientError(Exception):
    """Base exception for every error in the client"""

    def __init__(self, *args, **kwargs):
        # Use *args/**kwargs to guard against TypeError: "got multiple values
        # for argument 'message'/'response'/'code'" when unpacking IG's JSON
        # with **data (almost every IG error JSON has a 'message' key)
        self.message = args[0] if args else kwargs.pop("message", "")
        self.response = kwargs.pop("response", None)
        self.code = kwargs.pop("code", None)
        # Keep extra fields from IG's JSON (e.g. challenge, two_factor_info)
        self.extra = kwargs
        super().__init__(self.message)

    def __str__(self) -> str:
        base = self.message or self.__class__.__name__
        if self.code:
            return f"[{self.code}] {base}"
        return base


# --- network / structural --------------------------------------------------
class ClientConnectionError(ClientError):
    """Network unreachable / timeout"""


class ClientThrottledError(ClientError):
    """Rate-limited (HTTP 429 or feedback_required of the throttle kind)"""


class ClientBadRequestError(ClientError):
    """Generic HTTP 400"""


class ClientForbiddenError(ClientError):
    """HTTP 403"""


class ClientNotFoundError(ClientError):
    """HTTP 404 / resource not found"""


class ClientJSONDecodeError(ClientError):
    """Response is not valid JSON"""


class ClientRequestTimeout(ClientConnectionError):
    """Request timeout"""


# --- auth / session --------------------------------------------------------
class AuthRequired(ClientError):
    """Not logged in yet, or the session has expired"""


class LoginRequired(AuthRequired):
    """IG returned login_required -> must relogin"""


class BadPassword(ClientError):
    """Incorrect password"""


class InvalidUser(ClientError):
    """No such username"""


class ConsentRequired(ClientError):
    """Consent must be accepted (GDPR, etc.)"""


class SentryBlock(ClientError):
    """Hit a sentry_block (suspicious behavior)"""


class RateLimitError(ClientThrottledError):
    """Rate limit"""


# --- client-side guards (raised by okgram itself, not by IG) ---------------
class RateLimitReached(ClientError):
    """The local rate governor blocked an action before it was sent (client-side
    safety brake to avoid IG's feedback_required / action blocks)."""


class EgressMismatch(ClientError):
    """The egress IP's region no longer matches the session's region -- sending
    would risk an instant challenge (raised by the consistency guard)."""


# --- two factor / challenge ------------------------------------------------
class TwoFactorRequired(ClientError):
    """2FA confirmation required — see self.extra['two_factor_info']"""


class ChallengeRequired(ClientError):
    """IG requires a challenge (identity verification) — see self.extra"""


class ChallengeError(ClientError):
    """An error occurred while completing a challenge"""


class ChallengeSelfieCaptcha(ChallengeError):
    """The challenge requires taking a selfie"""


class ChallengeUnknownStep(ChallengeError):
    """An unsupported challenge step"""


class RecaptchaChallengeForm(ChallengeError):
    """The challenge requires solving a recaptcha"""


class CheckpointRequired(ChallengeRequired):
    """checkpoint_required"""


# --- feedback / action block ----------------------------------------------
class FeedbackRequired(ClientError):
    """IG temporarily blocked the action (action blocked) — see feedback_message"""


class PleaseWaitFewMinutes(FeedbackRequired):
    """'Please wait a few minutes before you try again.'"""


class UserActionRequired(ClientError):
    """The user must do something first"""


# --- media / content -------------------------------------------------------
class MediaError(ClientError):
    """Media-related error"""


class MediaNotFound(MediaError, ClientNotFoundError):
    """Media not found"""


class UserNotFound(InvalidUser, ClientNotFoundError):
    """User not found"""


class CollectionNotFound(ClientNotFoundError):
    """Collection not found"""


class DirectThreadNotFound(ClientNotFoundError):
    """Thread not found in direct"""


class HashtagNotFound(ClientNotFoundError):
    """Hashtag not found"""


class LocationNotFound(ClientNotFoundError):
    """Location not found"""


class PrivateAccount(ClientError):
    """Account is private, its data cannot be accessed"""


# --- upload ----------------------------------------------------------------
class UploadError(MediaError):
    """Media upload failed"""


class VideoConfigureError(UploadError):
    """Video configure failed (often retryable)"""


class PhotoConfigureError(UploadError):
    """Photo configure failed"""


# ---------------------------------------------------------------------------
# Helper that maps IG's error JSON -> an exception class
# ---------------------------------------------------------------------------
def map_exception(message: str, json_data: dict, response=None) -> ClientError:
    """
    Take the message + JSON returned by IG and return the most appropriate
    exception (does not raise yet — the caller raises it).
    """
    data = json_data or {}
    msg = (message or data.get("message") or "").strip()
    msg_l = msg.lower()
    error_type = (data.get("error_type") or "").lower()
    code = response.status_code if response is not None else data.get("status_code")

    def make(exc_cls):
        # Filter out keys already passed directly to avoid duplicate keywords on **data
        extra = {k: v for k, v in data.items() if k not in ("message", "response", "code")}
        return exc_cls(msg or exc_cls.__name__, response=response, code=code, **extra)

    # Order matters: specific first, broad later
    if "challenge_required" in msg_l or data.get("challenge"):
        return make(ChallengeRequired)
    if "checkpoint_required" in msg_l or "checkpoint" in error_type:
        return make(CheckpointRequired)
    if data.get("two_factor_required") or "two_factor" in msg_l:
        return make(TwoFactorRequired)
    if "login_required" in msg_l or error_type == "login_required":
        return make(LoginRequired)
    if "bad_password" in error_type or "password you entered" in msg_l:
        return make(BadPassword)
    if "invalid_user" in error_type or "username you entered" in msg_l:
        return make(InvalidUser)
    if "consent_required" in msg_l:
        return make(ConsentRequired)
    if "sentry_block" in error_type or "sentry" in msg_l:
        return make(SentryBlock)
    if "please wait a few minutes" in msg_l:
        return make(PleaseWaitFewMinutes)
    if "feedback_required" in msg_l or error_type == "feedback_required":
        return make(FeedbackRequired)
    if "rate" in error_type and "limit" in error_type:
        return make(RateLimitError)
    if "media not found" in msg_l or "media_id" in msg_l and "not" in msg_l:
        return make(MediaNotFound)
    if "user not found" in msg_l:
        return make(UserNotFound)
    if "not authorized to view user" in msg_l:
        return make(PrivateAccount)

    # Based on HTTP status
    if code == 429:
        return make(ClientThrottledError)
    if code == 404:
        return make(ClientNotFoundError)
    if code == 403:
        return make(ClientForbiddenError)
    if code == 400:
        return make(ClientBadRequestError)

    return make(ClientError)
