"""
okgram — Instagram Private API client (Python)

reverse-engineered from Instagram Lite 516.0.0.8.103 + Instagram Android private API
works with the i.instagram.com/api/v1 backend, the same one as the real app

Example:
    from okgram import OkGram          # or: from okgram import InstagramAPI

    cl = OkGram()
    cl.login("user", "pass")
    print(cl.user_info_by_username_v1("instagram"))
"""
from . import (
    behaviors,
    config,
    doctor,
    exceptions,
    fingerprint,
    geo,
    guard,
    limits,
    live_config,
    store,
)
from .client import InstagramAPI
from .device import Device
from .geo import GeoProfile
from .limits import RateGovernor
from .store import SessionStore
from .exceptions import (
    BadPassword,
    ChallengeRequired,
    ClientError,
    FeedbackRequired,
    LoginRequired,
    TwoFactorRequired,
)

# Branded aliases — all three names refer to the same client class.
OkGram = InstagramAPI
Client = InstagramAPI

__version__ = "1.2.0"
__all__ = [
    "OkGram",
    "Client",
    "InstagramAPI",
    "Device",
    "GeoProfile",
    "RateGovernor",
    "SessionStore",
    "config",
    "exceptions",
    "geo",
    "doctor",
    "behaviors",
    "live_config",
    "fingerprint",
    "guard",
    "limits",
    "store",
    "ClientError",
    "LoginRequired",
    "BadPassword",
    "TwoFactorRequired",
    "ChallengeRequired",
    "FeedbackRequired",
]

