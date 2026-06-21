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
from . import config, exceptions
from .client import InstagramAPI
from .device import Device
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

__version__ = "1.0.0"
__all__ = [
    "OkGram",
    "Client",
    "InstagramAPI",
    "Device",
    "config",
    "exceptions",
    "ClientError",
    "LoginRequired",
    "BadPassword",
    "TwoFactorRequired",
    "ChallengeRequired",
    "FeedbackRequired",
]

