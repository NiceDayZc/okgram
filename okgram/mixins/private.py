"""
PrivateRequestMixin — the core of all request dispatching

Every endpoint mixin calls through these 2 methods:
    self.private_request(endpoint, data=..., params=...)   # mobile API (i.instagram.com/api/v1)
    self.public_request(path, params=...)                  # web API (www.instagram.com)

Key contract:
    - private_request: data=None  -> GET ; data=dict/str -> POST (signed_body)
    - returns a dict already parsed from JSON (response.json())
    - IG errors are converted into exceptions in exceptions.py and raised
    - token/headers (authorization, www-claim, mid) are updated automatically from the response
"""
from __future__ import annotations

import logging
import time
from json import JSONDecodeError
from typing import Any, Dict, Optional, Union

from .. import config, guard, utils
from ..exceptions import (
    ClientError,
    ClientConnectionError,
    ClientForbiddenError,
    ClientJSONDecodeError,
    ClientNotFoundError,
    ClientThrottledError,
    EgressMismatch,
    FeedbackRequired,
    map_exception,
)

logger = logging.getLogger("okgram")


class PrivateRequestMixin:
    """Bundles request dispatching logic + header/token/retry/error handling"""

    # ---- attributes the main client must set (see client.py) ----------------
    device: Any
    session: Any
    authorization: str = ""
    user_id: Optional[str] = None
    username: Optional[str] = None
    mid: str = ""
    ig_www_claim: str = "0"
    csrftoken: str = ""
    # IG-U-* session-routing headers. IG sets these (ig-set-ig-u-*) and expects the
    # client to echo them back on EVERY subsequent request; not doing so breaks
    # session continuity and is a top cause of "login_required" bounces.
    ig_u_rur: str = ""
    ig_u_shbid: str = ""
    ig_u_shbts: str = ""
    ig_direct_region_hint: str = ""
    locale: str = config.LOCALE
    country: str = config.DEFAULT_COUNTRY
    country_code: int = config.DEFAULT_COUNTRY_CODE
    timezone_offset: int = config.TIMEZONE_OFFSET
    eu_dc_enabled: str = config.EU_DC_ENABLED
    app_version: str = config.APP_VERSION
    version_code: str = config.VERSION_CODE
    bloks_version_id: str = config.BLOKS_VERSION_ID
    mode: str = config.MODE_MOBILE
    nav_chain: str = ""
    delay_range: tuple = config.REQUEST_DELAY_RANGE
    request_timeout: int = config.REQUEST_TIMEOUT
    max_retries: int = config.MAX_RETRIES

    # keep the latest response for debugging
    last_response: Optional[Any] = None
    last_json: Dict = {}
    last_response_ts: float = 0.0

    # ------------------------------------------------------------------
    # header construction
    # ------------------------------------------------------------------
    @property
    def base_headers(self) -> Dict[str, str]:
        """Request headers -- mobile (Android app) or web (browser) per ``self.mode``."""
        if getattr(self, "mode", config.MODE_MOBILE) == config.MODE_WEB:
            return self._web_base_headers()
        return self._mobile_base_headers()

    def _mobile_base_headers(self) -> Dict[str, str]:
        ua = self.device.user_agent(self.app_version, self.version_code, self.locale)
        # Pigeon session id is ONE id per app session (stable across requests).
        # Regenerating it per request — as before — is an obvious bot signal, so
        # keep it on the client and reuse it for the instance's lifetime.
        if not getattr(self, "pigeon_session_id", None):
            self.pigeon_session_id = config.PIGEON_SESSION_PREFIX + utils.generate_uuid()
        bloks = getattr(self, "bloks_version_id", None) or config.BLOKS_VERSION_ID
        headers = {
            "X-IG-App-Locale": self.locale,
            "X-IG-Device-Locale": self.locale,
            "X-IG-Mapped-Locale": self.locale,
            "X-IG-Nav-Chain": self.nav_chain or "",
            "X-Pigeon-Session-Id": self.pigeon_session_id,
            "X-Pigeon-Rawclienttime": f"{time.time():.3f}",
            "X-IG-Bandwidth-Speed-KBPS": "-1.000",
            "X-IG-Bandwidth-TotalBytes-B": "0",
            "X-IG-Bandwidth-TotalTime-MS": "0",
            "X-IG-App-Startup-Country": self.country,
            "X-Bloks-Version-Id": bloks,
            "X-IG-WWW-Claim": self.ig_www_claim or "0",
            "X-Bloks-Is-Layout-RTL": "false",
            "X-Bloks-Is-Panorama-Enabled": "true",
            "X-IG-Device-ID": self.device.uuid,
            "X-IG-Family-Device-ID": self.device.family_device_id,
            "X-IG-Android-ID": self.device.device_id,
            "X-IG-Timezone-Offset": str(self.timezone_offset),
            "X-IG-Connection-Type": config.CONNECTION_TYPE,
            "X-IG-EU-DC-ENABLED": str(getattr(self, "eu_dc_enabled", config.EU_DC_ENABLED)),
            "X-IG-Capabilities": config.CAPABILITIES,
            "X-IG-App-ID": config.APP_ID,
            "X-ASBD-ID": config.ASBD_ID,
            "Priority": "u=3",
            "User-Agent": ua,
            "Accept-Language": config.ACCEPT_LANGUAGE,
            # NOTE: no "Host"/"Connection" headers — over HTTP/2 the host travels
            # in the :authority pseudo-header and hop-by-hop headers are illegal;
            # the transport/engine manages the connection.
            "Accept-Encoding": "gzip, deflate, br",
            "X-FB-HTTP-Engine": "Liger",
            "X-FB-Client-IP": "True",
            "X-FB-Server-Cluster": "True",
            "X-FB-Connection-Type": config.FB_CONNECTION_TYPE,
        }
        # X-IG-Nav-Chain is omitted entirely (not sent empty) when we have no chain.
        if not headers["X-IG-Nav-Chain"]:
            headers.pop("X-IG-Nav-Chain")
        if self.mid:
            headers["X-MID"] = self.mid
        if self.csrftoken:
            headers["X-CSRFToken"] = self.csrftoken
        # after login a Bearer token is present
        if self.authorization:
            headers["Authorization"] = self.authorization
            if self.user_id:
                headers["IG-U-DS-USER-ID"] = str(self.user_id)
                headers["IG-INTENDED-USER-ID"] = str(self.user_id)
        # echo the session-routing headers back (continuity -> fewer bounces)
        self._attach_routing_headers(headers)
        return headers

    def _web_base_headers(self) -> Dict[str, str]:
        """Browser-style headers for a web-origin session (www.instagram.com)."""
        headers = {
            "User-Agent": config.WEB_USER_AGENT,
            "Accept": "*/*",
            "Accept-Language": f"{config.ACCEPT_LANGUAGE},en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "X-IG-App-ID": config.WEB_APP_ID,
            "X-ASBD-ID": config.ASBD_ID,
            "X-IG-WWW-Claim": self.ig_www_claim or "0",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": f"https://{config.WEB_DOMAIN}",
            "Referer": f"https://{config.WEB_DOMAIN}/",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
        }
        if self.mid:
            headers["X-MID"] = self.mid
        if self.csrftoken:
            headers["X-CSRFToken"] = self.csrftoken
        self._attach_routing_headers(headers)
        return headers

    def _attach_routing_headers(self, headers: Dict[str, str]) -> None:
        """Echo IG-U-* routing headers (set by the server) on outbound requests."""
        if self.user_id and "IG-U-DS-USER-ID" not in headers:
            headers["IG-U-DS-USER-ID"] = str(self.user_id)
        if self.ig_u_rur:
            headers["IG-U-RUR"] = self.ig_u_rur
        if self.ig_u_shbid:
            headers["IG-U-SHBID"] = self.ig_u_shbid
        if self.ig_u_shbts:
            headers["IG-U-SHBTS"] = self.ig_u_shbts
        if self.ig_direct_region_hint:
            headers["IG-U-IG-DIRECT-REGION-HINT"] = self.ig_direct_region_hint

    @property
    def public_headers(self) -> Dict[str, str]:
        """headers for the web API (www.instagram.com)"""
        # Web requests always look like the browser web client regardless of mode.
        headers = {
            "User-Agent": config.WEB_USER_AGENT,
            "Accept": "*/*",
            "Accept-Language": f"{config.ACCEPT_LANGUAGE},en;q=0.9",
            "X-IG-App-ID": config.WEB_APP_ID,
            "X-ASBD-ID": config.ASBD_ID,
            "X-IG-WWW-Claim": self.ig_www_claim or "0",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": f"https://{config.WEB_DOMAIN}",
            "Referer": f"https://{config.WEB_DOMAIN}/",
        }
        if self.csrftoken:
            headers["X-CSRFToken"] = self.csrftoken
        self._attach_routing_headers(headers)
        return headers

    # ------------------------------------------------------------------
    # private (mobile) request
    # ------------------------------------------------------------------
    def private_request(
        self,
        endpoint: str,
        data: Optional[Union[Dict[str, Any], str]] = None,
        params: Optional[Dict[str, Any]] = None,
        *,
        login: bool = False,
        with_signature: bool = True,
        headers: Optional[Dict[str, str]] = None,
        domain: Optional[str] = None,
        raw_form: bool = False,
        retries: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Send a request to i.instagram.com/api/v1/<endpoint>

        Parameters
        ----------
        endpoint : str
            path after /api/v1/, e.g. 'users/<pk>/info/'
            (if it starts with http, that url is used directly)
        data : dict | str | None
            None    -> GET
            dict    -> POST as signed_body (unless raw_form=True)
            str     -> POST as signed_body of that json string
        params : dict | None
            query string (works for both GET/POST)
        login : bool
            during login there is no authorization token yet
        with_signature : bool
            False = send data as a plain form (no signing)
        raw_form : bool
            True = send data as form-urlencoded directly (no signed_body wrapping)
        """
        if endpoint.startswith("http"):
            url = endpoint
        else:
            # web mode talks to www.instagram.com/api/v1 (origin-consistent with a
            # browser sessionid); mobile mode talks to i.instagram.com/api/v1.
            if getattr(self, "mode", config.MODE_MOBILE) == config.MODE_WEB:
                base = config.WEB_API_URL
            else:
                base = config.BASE_API_URL
            if domain:
                base = f"https://{domain}/api/{config.API_VERSION}/"
            url = base + endpoint.lstrip("/")

        req_headers = dict(self.base_headers)
        if headers:
            req_headers.update(headers)

        # prepare body
        body = None
        if data is not None:
            if raw_form:
                body = data if isinstance(data, dict) else {"data": data}
            elif with_signature:
                body = utils.generate_signed_body(data)
            else:
                body = data if isinstance(data, dict) else {"signed_body": data}

        method = "POST" if data is not None else "GET"
        # match the app deterministically: form-encoded body for signed POSTs
        if method == "POST" and "Content-Type" not in req_headers:
            req_headers["Content-Type"] = (
                "application/x-www-form-urlencoded; charset=UTF-8"
            )
        max_try = self.max_retries if retries is None else retries
        last_exc: Optional[Exception] = None

        # rate governor: gate write actions ONCE before sending (reads pass through).
        # May sleep (human pacing) or raise RateLimitReached -- both intended.
        gov = getattr(self, "governor", None)
        if gov is not None and method == "POST" and not login:
            gov.gate(endpoint)

        # egress guard: verify the IP region matches the session ONCE before the
        # first write (a sudden country change is an instant-challenge trigger).
        # Lazy + once-per-session so it doesn't add a geo lookup to every request.
        if (getattr(self, "guard_policy", None) and method == "POST" and not login
                and not getattr(self, "_egress_checked", False)):
            self._egress_checked = True
            try:
                guard.verify_egress(self, policy=self.guard_policy)
            except EgressMismatch:
                raise
            except Exception:  # noqa: BLE001 -- a failed geo lookup must not block
                logger.debug("egress guard check skipped", exc_info=True)

        for attempt in range(max_try + 1):
            # random delay to mimic human behavior (skip the first login attempt for speed)
            if self.delay_range and not (login and attempt == 0):
                utils.random_delay(self.delay_range)
            try:
                resp = self.session.request(
                    method,
                    url,
                    params=params,
                    data=body,
                    headers=req_headers,
                    timeout=self.request_timeout,
                )
                self.last_response = resp
                self.last_response_ts = time.time()
                self._update_from_response_headers(resp)
                result = self._parse_response(resp, endpoint)
                if gov is not None:
                    gov.note_success()
                return result

            except FeedbackRequired:
                # an action block -- DON'T retry (retrying makes it worse); let the
                # governor back off, then propagate so the caller can pause.
                if gov is not None:
                    gov.note_block()
                raise

            except (ClientThrottledError, ClientConnectionError) as exc:
                last_exc = exc
                if isinstance(exc, ClientThrottledError) and gov is not None:
                    gov.note_block()
                if attempt >= max_try:
                    raise
                # smart backoff: honour Retry-After when IG sends it, else exp+jitter
                wait = guard.retry_wait(exc, attempt)
                logger.warning(
                    "request %s failed (%s) retry in %.1fs", endpoint, exc, wait
                )
                time.sleep(wait)
            # transport normalises timeouts/network errors to
            # ClientRequestTimeout (subclass of ClientConnectionError), so the
            # except above already handles them (and retries).

        if last_exc:
            raise last_exc
        return {}

    # ------------------------------------------------------------------
    # public (web) request
    # ------------------------------------------------------------------
    def public_request(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        *,
        headers: Optional[Dict[str, str]] = None,
        full_url: bool = False,
    ) -> Dict[str, Any]:
        """Send a request to www.instagram.com (web API / graphql)"""
        url = path if full_url else (config.WEB_API_URL + path.lstrip("/"))
        req_headers = dict(self.public_headers)
        if headers:
            req_headers.update(headers)
        method = "POST" if data is not None else "GET"

        last_exc = None
        for attempt in range(self.max_retries + 1):
            if self.delay_range:
                utils.random_delay(self.delay_range)
            try:
                resp = self.session.request(
                    method, url, params=params, data=data,
                    headers=req_headers, timeout=self.request_timeout,
                )
                self.last_response = resp
                self._update_from_response_headers(resp)
                return self._parse_response(resp, path)
            except (ClientThrottledError, ClientConnectionError) as exc:
                last_exc = exc
                if attempt >= self.max_retries:
                    raise
                time.sleep(config.RETRY_BACKOFF * (attempt + 1))
        if last_exc:
            raise last_exc
        return {}

    # ------------------------------------------------------------------
    # graphql
    # ------------------------------------------------------------------
    def graphql_request(
        self, query_hash: str, variables: Union[dict, str]
    ) -> Dict[str, Any]:
        """Send a GraphQL query to www.instagram.com/graphql/query/"""
        if isinstance(variables, dict):
            variables = utils.json_dumps(variables)
        params = {"query_hash": query_hash, "variables": variables}
        return self.public_request(
            config.GRAPHQL_URL, params=params, full_url=True
        )

    # ------------------------------------------------------------------
    # internal helpers
    # ------------------------------------------------------------------
    def _update_from_response_headers(self, resp: Any) -> None:
        """
        Adopt the live session state IG hands back in response headers: the auth
        token, www-claim, mid, user id, and -- crucially -- the IG-U-* routing
        headers that must be echoed on every later request to keep the session
        alive. An ``ig-set-authorization`` of the literal value ``"0"`` means
        "clear it", which we honour.
        """
        h = resp.headers
        set_auth = h.get("ig-set-authorization")
        if set_auth:
            # IG sends "Bearer IGT:2:<blob>" to set the token, or exactly "0" to
            # clear it. Only "0" clears -- any non-zero value is a real token.
            self.authorization = "" if set_auth.strip() == "0" else set_auth
        if h.get("x-ig-set-www-claim"):
            self.ig_www_claim = h["x-ig-set-www-claim"]
        if h.get("ig-set-x-mid"):
            self.mid = h["ig-set-x-mid"]
        if h.get("ig-set-ig-u-ds-user-id"):
            self.user_id = h["ig-set-ig-u-ds-user-id"]
        # IG-U-* session-routing headers (echoed back by _attach_routing_headers)
        if h.get("ig-set-ig-u-rur"):
            self.ig_u_rur = h["ig-set-ig-u-rur"]
        if h.get("ig-set-ig-u-shbid"):
            self.ig_u_shbid = h["ig-set-ig-u-shbid"]
        if h.get("ig-set-ig-u-shbts"):
            self.ig_u_shbts = h["ig-set-ig-u-shbts"]
        if h.get("ig-set-ig-u-ig-direct-region-hint"):
            self.ig_direct_region_hint = h["ig-set-ig-u-ig-direct-region-hint"]
        # csrftoken + rur also arrive as cookies -- keep both in sync.
        jar = self.session.cookies
        token = resp.cookies.get("csrftoken") or jar.get("csrftoken")
        if token:
            self.csrftoken = token
        rur_cookie = resp.cookies.get("rur") or jar.get("rur")
        if rur_cookie and not self.ig_u_rur:
            self.ig_u_rur = rur_cookie
        mid_cookie = resp.cookies.get("mid") or jar.get("mid")
        if mid_cookie and not self.mid:
            self.mid = mid_cookie

    def _parse_response(
        self, resp: Any, endpoint: str
    ) -> Dict[str, Any]:
        """parse JSON + check for errors + raise the appropriate exception"""
        status = resp.status_code

        # parse json (IG sometimes returns html when blocking)
        try:
            data = resp.json()
            self.last_json = data
        except JSONDecodeError:
            text = (resp.text or "")[:500]
            if status >= 500:
                raise ClientConnectionError(
                    f"server error {status} at {endpoint}", response=resp, code=status
                )
            raise ClientJSONDecodeError(
                f"response is not JSON ({status}) at {endpoint}: {text}",
                response=resp, code=status,
            )

        # some endpoints (graphql/web) return a list -> treat as success, not an error dict
        if not isinstance(data, dict):
            if status < 400:
                return data
            raise ClientError(
                f"unexpected response ({status}) at {endpoint}",
                response=resp, code=status,
            )

        # 2xx + status ok -> success
        if status < 400 and data.get("status") != "fail":
            return data

        # there is an error -> convert to an exception; filter keys already passed directly to avoid duplicate keyword
        message = data.get("message") or data.get("error_title") or ""
        extra = {k: v for k, v in data.items() if k not in ("message", "response", "code")}
        if status == 429:
            raise ClientThrottledError(
                message or "rate limited", response=resp, code=status, **extra
            )
        if status == 404:
            raise ClientNotFoundError(
                message or "not found", response=resp, code=status, **extra
            )
        if status == 403 and "login_required" not in str(message).lower():
            # a 403 that is not login_required may be a generic forbidden
            exc = map_exception(message, data, resp)
            if type(exc).__name__ == "ClientError":
                raise ClientForbiddenError(
                    message or "forbidden", response=resp, code=status, **extra
                )
            raise exc

        raise map_exception(message, data, resp)
