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

from .. import config, utils
from ..exceptions import (
    ClientError,
    ClientConnectionError,
    ClientForbiddenError,
    ClientJSONDecodeError,
    ClientNotFoundError,
    ClientThrottledError,
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
    locale: str = config.LOCALE
    country: str = "US"
    country_code: int = 1
    timezone_offset: int = config.TIMEZONE_OFFSET
    app_version: str = config.APP_VERSION
    version_code: str = config.VERSION_CODE
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
        ua = self.device.user_agent(self.app_version, self.version_code, self.locale)
        # Pigeon session id is ONE id per app session (stable across requests).
        # Regenerating it per request — as before — is an obvious bot signal, so
        # keep it on the client and reuse it for the instance's lifetime.
        if not getattr(self, "pigeon_session_id", None):
            self.pigeon_session_id = config.PIGEON_SESSION_PREFIX + utils.generate_uuid()
        headers = {
            "X-IG-App-Locale": self.locale,
            "X-IG-Device-Locale": self.locale,
            "X-IG-Mapped-Locale": self.locale,
            "X-Pigeon-Session-Id": self.pigeon_session_id,
            "X-Pigeon-Rawclienttime": f"{time.time():.3f}",
            "X-IG-Bandwidth-Speed-KBPS": "-1.000",
            "X-IG-Bandwidth-TotalBytes-B": "0",
            "X-IG-Bandwidth-TotalTime-MS": "0",
            "X-IG-App-Startup-Country": self.country,
            "X-Bloks-Version-Id": config.BLOKS_VERSION_ID,
            "X-IG-WWW-Claim": self.ig_www_claim or "0",
            "X-Bloks-Is-Layout-RTL": "false",
            "X-Bloks-Is-Panorama-Enabled": "true",
            "X-IG-Device-ID": self.device.uuid,
            "X-IG-Family-Device-ID": self.device.family_device_id,
            "X-IG-Android-ID": self.device.device_id,
            "X-IG-Timezone-Offset": str(self.timezone_offset),
            "X-IG-Connection-Type": config.CONNECTION_TYPE,
            "X-IG-Capabilities": config.CAPABILITIES,
            "X-IG-App-ID": config.APP_ID,
            "Priority": "u=3",
            "User-Agent": ua,
            "Accept-Language": config.ACCEPT_LANGUAGE,
            "Accept-Encoding": "gzip, deflate",
            # NOTE: no "Host"/"Connection" headers — over HTTP/2 the host travels
            # in the :authority pseudo-header and hop-by-hop headers are illegal;
            # the transport/engine manages the connection.
            "X-FB-HTTP-Engine": "Liger",
            "X-FB-Client-IP": "True",
            "X-FB-Server-Cluster": "True",
        }
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
        return headers

    @property
    def public_headers(self) -> Dict[str, str]:
        """headers for the web API (www.instagram.com)"""
        ua = self.device.user_agent(self.app_version, self.version_code, self.locale)
        headers = {
            "User-Agent": ua,
            "Accept": "*/*",
            "Accept-Language": config.ACCEPT_LANGUAGE,
            "X-IG-App-ID": config.APP_ID,
            "X-ASBD-ID": "129477",
            "X-IG-WWW-Claim": self.ig_www_claim or "0",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": f"https://{config.WEB_DOMAIN}",
            "Referer": f"https://{config.WEB_DOMAIN}/",
        }
        if self.csrftoken:
            headers["X-CSRFToken"] = self.csrftoken
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
        max_try = self.max_retries if retries is None else retries
        last_exc: Optional[Exception] = None

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
                return self._parse_response(resp, endpoint)

            except (ClientThrottledError, ClientConnectionError) as exc:
                last_exc = exc
                if attempt >= max_try:
                    raise
                wait = config.RETRY_BACKOFF * (attempt + 1)
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
        """Pull new token/claim/mid from the response headers"""
        h = resp.headers
        if h.get("ig-set-authorization"):
            self.authorization = h["ig-set-authorization"]
        if h.get("x-ig-set-www-claim"):
            self.ig_www_claim = h["x-ig-set-www-claim"]
        if h.get("ig-set-x-mid"):
            self.mid = h["ig-set-x-mid"]
        if h.get("ig-set-ig-u-ds-user-id"):
            self.user_id = h["ig-set-ig-u-ds-user-id"]
        # csrftoken comes with the cookie
        token = resp.cookies.get("csrftoken") or self.session.cookies.get("csrftoken")
        if token:
            self.csrftoken = token

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
