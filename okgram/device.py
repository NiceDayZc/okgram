"""
Create/manage a simulated Android "device profile"

These values must stay constant for the lifetime of the account (persisted in
settings), because frequently changing the device makes IG consider it
suspicious and triggers challenges more often.
"""
from __future__ import annotations

import random
from typing import Dict, Optional

from . import config, utils

# Set of common real Android devices (manufacturer, model, device, cpu, dpi, resolution)
DEVICE_POOL = [
    {
        "manufacturer": "samsung", "model": "SM-G991B", "device": "o1s",
        "cpu": "exynos2100", "dpi": "420dpi", "resolution": "1080x2241",
        "android_version": 33, "android_release": "13",
    },
    {
        "manufacturer": "samsung", "model": "SM-G998B", "device": "p3s",
        "cpu": "exynos2100", "dpi": "560dpi", "resolution": "1440x3008",
        "android_version": 33, "android_release": "13",
    },
    {
        "manufacturer": "Xiaomi", "model": "M2101K6G", "device": "sweet",
        "cpu": "qcom", "dpi": "440dpi", "resolution": "1080x2300",
        "android_version": 31, "android_release": "12",
    },
    {
        "manufacturer": "OnePlus", "model": "IN2023", "device": "OnePlus8Pro",
        "cpu": "qcom", "dpi": "420dpi", "resolution": "1440x3168",
        "android_version": 30, "android_release": "11",
    },
    {
        "manufacturer": "Google", "model": "Pixel 6", "device": "oriole",
        "cpu": "gs101", "dpi": "420dpi", "resolution": "1080x2400",
        "android_version": 33, "android_release": "13",
    },
    {
        "manufacturer": "samsung", "model": "SM-A536B", "device": "a53x",
        "cpu": "s5e8825", "dpi": "450dpi", "resolution": "1080x2400",
        "android_version": 33, "android_release": "13",
    },
]


class Device:
    """
    Holds the simulated device data + builds the User-Agent

    Parameters
    ----------
    seed : str | None
        If provided (e.g. username), the same device + uuid set is produced
        every time (deterministic). Good for binding one device to one account.
    profile : dict | None
        Lets you specify a device profile yourself (overrides DEVICE_POOL).
    """

    def __init__(self, seed: Optional[str] = None, profile: Optional[dict] = None):
        self.seed = seed
        rng = random.Random(seed) if seed is not None else random.Random()

        base = profile or rng.choice(DEVICE_POOL)
        self.profile: Dict = dict(base)

        # The various uuids that must stay constant per device
        self.uuid = self._seeded_uuid(rng, "uuid")
        self.phone_id = self._seeded_uuid(rng, "phone")
        self.client_session_id = self._seeded_uuid(rng, "session")
        self.advertising_id = self._seeded_uuid(rng, "ad")
        self.device_id = utils.generate_android_device_id(
            seed if seed is not None else self.uuid
        )
        # family device id (shared across the facebook family of apps)
        self.family_device_id = self._seeded_uuid(rng, "family")
        self.request_id = utils.generate_uuid()

    @staticmethod
    def _seeded_uuid(rng: random.Random, salt: str) -> str:
        """Generate a deterministic uuid from rng (same value for the same seed)"""
        hex_str = "".join(rng.choice("0123456789abcdef") for _ in range(32))
        return (
            f"{hex_str[:8]}-{hex_str[8:12]}-{hex_str[12:16]}-"
            f"{hex_str[16:20]}-{hex_str[20:32]}"
        )

    # ------------------------------------------------------------------
    def user_agent(
        self,
        app_version: str = config.APP_VERSION,
        version_code: str = config.VERSION_CODE,
        locale: str = config.LOCALE,
    ) -> str:
        """Build the Instagram Android User-Agent"""
        p = self.profile
        return config.USER_AGENT_TEMPLATE.format(
            app_version=app_version,
            android_version=p["android_version"],
            android_release=p["android_release"],
            dpi=p["dpi"],
            resolution=p["resolution"],
            manufacturer=p["manufacturer"],
            model=p["model"],
            device=p["device"],
            cpu=p["cpu"],
            locale=locale,
            version_code=version_code,
        )

    # ------------------------------------------------------------------
    def to_dict(self) -> dict:
        """Serialize into settings"""
        return {
            "profile": self.profile,
            "uuid": self.uuid,
            "phone_id": self.phone_id,
            "client_session_id": self.client_session_id,
            "advertising_id": self.advertising_id,
            "device_id": self.device_id,
            "family_device_id": self.family_device_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Device":
        """Restore from settings"""
        obj = cls.__new__(cls)
        obj.seed = None
        obj.profile = data["profile"]
        obj.uuid = data["uuid"]
        obj.phone_id = data["phone_id"]
        obj.client_session_id = data["client_session_id"]
        obj.advertising_id = data["advertising_id"]
        obj.device_id = data["device_id"]
        obj.family_device_id = data.get("family_device_id", utils.generate_uuid())
        obj.request_id = utils.generate_uuid()
        return obj

    # The device fields that many endpoints must attach in the payload
    def payload_fields(self) -> dict:
        p = self.profile
        return {
            "device_id": self.device_id,
            "_uuid": self.uuid,
            "android_device_id": self.device_id,
            "phone_id": self.phone_id,
            "device_brand": p["manufacturer"],
            "device_model": p["model"],
            "os_version": str(p["android_version"]),
            "os_release": p["android_release"],
        }
