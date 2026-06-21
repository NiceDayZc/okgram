"""
AccountMixin — manage your own account/settings

Covers: view current account info, edit profile (name/bio/url/email/phone/gender),
set the account to private/public, change password, change/remove profile picture,
view security info (2FA), basic notification settings, etc.

Note: this is a mixin so it has no __init__ — state/request-issuing methods come from the
main class (InstagramAPI) via multiple inheritance
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .. import config, utils
from ..exceptions import ClientError


class AccountMixin:
    """Collection of methods related to your own account and settings"""

    # attributes already provided by the main class (declared only for type hints)
    user_id: Optional[str]
    username: Optional[str]
    device: Any
    last_json: Dict[str, Any]

    # ------------------------------------------------------------------
    # View current account info
    # ------------------------------------------------------------------
    def get_current_user(self) -> Dict[str, Any]:
        """Fetch info for the logged-in account (edit mode to get the full set of editable fields)"""
        result = self.private_request(
            "accounts/current_user/", params={"edit": "true"}
        )
        return result.get("user", {})

    def account_info(self) -> Dict[str, Any]:
        """alias of get_current_user() — returns the current account info dict"""
        return self.get_current_user()

    def get_account_settings(self) -> Dict[str, Any]:
        """Fetch the full JSON of accounts/current_user/ (including fields beyond user)"""
        return self.private_request(
            "accounts/current_user/", params={"edit": "true"}
        )

    # ------------------------------------------------------------------
    # Edit profile
    # ------------------------------------------------------------------
    def edit_profile(self, **fields: Any) -> Dict[str, Any]:
        """
        Edit the profile: take current values as the base then override with the fields passed in
        (first_name, username, biography, external_url, email, phone_number, gender)
        Returns the updated user info dict
        """
        current = self.get_current_user()

        # gender: 1=male, 2=female, 3=unspecified/custom
        data: Dict[str, Any] = {
            "external_url": current.get("external_url", ""),
            "phone_number": current.get("phone_number", ""),
            "username": current.get("username", self.username or ""),
            "first_name": current.get("full_name", ""),
            "biography": current.get("biography", ""),
            "email": current.get("email", ""),
            "gender": current.get("gender", 3),
        }
        # override with the values passed by the caller (only those that are not None)
        for key, value in fields.items():
            if value is not None:
                data[key] = value

        data.update({
            "_uuid": self.device.uuid,
            "_uid": self.user_id,
            "device_id": self.device.device_id,
        })
        result = self.private_request("accounts/edit_profile/", data)
        return result.get("user", result)

    def set_name(self, full_name: str) -> Dict[str, Any]:
        """Set the display name (full name) of the account"""
        return self.edit_profile(first_name=full_name)

    def set_username(self, username: str) -> Dict[str, Any]:
        """Change the username of the account"""
        return self.edit_profile(username=username)

    def set_biography(self, text: str) -> Dict[str, Any]:
        """Set the bio as raw text -> returns the user dict"""
        data = {
            "raw_text": text,
            "_uuid": self.device.uuid,
            "_uid": self.user_id,
        }
        result = self.private_request("accounts/set_biography/", data)
        return result.get("user", result)

    def set_external_url(self, url: str) -> Dict[str, Any]:
        """Set the website link (external url) in the profile"""
        return self.edit_profile(external_url=url)

    def set_gender(self, gender: int) -> Dict[str, Any]:
        """Set the gender (1=male, 2=female, 3=unspecified) in the profile"""
        return self.edit_profile(gender=gender)

    def set_phone_number(self, phone_number: str) -> Dict[str, Any]:
        """Set the phone number in the profile"""
        return self.edit_profile(phone_number=phone_number)

    def set_email(self, email: str) -> Dict[str, Any]:
        """Set the email in the profile"""
        return self.edit_profile(email=email)

    # ------------------------------------------------------------------
    # Privacy settings (private/public)
    # ------------------------------------------------------------------
    def account_set_private(self) -> Dict[str, Any]:
        """Set the account to private -> returns the user dict"""
        data = {"_uuid": self.device.uuid, "_uid": self.user_id}
        result = self.private_request("accounts/set_private/", data)
        return result.get("user", result)

    def account_set_public(self) -> Dict[str, Any]:
        """Set the account to public -> returns the user dict"""
        data = {"_uuid": self.device.uuid, "_uid": self.user_id}
        result = self.private_request("accounts/set_public/", data)
        return result.get("user", result)

    # ------------------------------------------------------------------
    # Password
    # ------------------------------------------------------------------
    def change_password(self, old_password: str, new_password: str) -> bool:
        """Change the password (encrypted with self.encrypt_password) -> True on success"""
        encrypt = getattr(self, "encrypt_password", None)
        if encrypt is None:
            raise ClientError("encrypt_password is missing — AuthMixin must be included")
        enc_new = encrypt(new_password)
        data = {
            "enc_old_password": encrypt(old_password),
            "enc_new_password1": enc_new,
            "enc_new_password2": enc_new,
            "_uuid": self.device.uuid,
            "_uid": self.user_id,
        }
        result = self.private_request("accounts/change_password/", data)
        return result.get("status") == "ok"

    # ------------------------------------------------------------------
    # Profile picture
    # ------------------------------------------------------------------
    def change_profile_picture(self, path: str) -> Dict[str, Any]:
        """Upload an image and set it as the new profile picture -> returns the user dict"""
        rupload = getattr(self, "photo_rupload", None)
        if rupload is None:
            raise ClientError("photo_rupload is missing — UploadMixin must be included")
        upload_result = rupload(path)
        # photo_rupload may return (upload_id, ...) or a dict or a str
        upload_id = self._extract_upload_id(upload_result)
        data = {
            "upload_id": upload_id,
            "_uuid": self.device.uuid,
            "_uid": self.user_id,
        }
        result = self.private_request("accounts/change_profile_picture/", data)
        return result.get("user", result)

    def remove_profile_picture(self) -> Dict[str, Any]:
        """Remove the current profile picture -> returns the user dict"""
        data = {"_uuid": self.device.uuid, "_uid": self.user_id}
        result = self.private_request("accounts/remove_profile_picture/", data)
        return result.get("user", result)

    @staticmethod
    def _extract_upload_id(upload_result: Any) -> str:
        """Extract the upload_id from the result of photo_rupload regardless of its format"""
        if isinstance(upload_result, str):
            return upload_result
        if isinstance(upload_result, dict):
            return str(upload_result.get("upload_id", ""))
        if isinstance(upload_result, (tuple, list)) and upload_result:
            first = upload_result[0]
            if isinstance(first, dict):
                return str(first.get("upload_id", ""))
            return str(first)
        return str(upload_result)

    # ------------------------------------------------------------------
    # Security / 2FA
    # ------------------------------------------------------------------
    def account_security_info(self) -> Dict[str, Any]:
        """Fetch the account's security info (2FA status, backup phone/email, etc.)"""
        data = {"_uuid": self.device.uuid, "_uid": self.user_id}
        return self.private_request("accounts/account_security_info/", data)

    def request_two_factor_enable(self) -> Dict[str, Any]:
        """Request to enable TOTP 2FA (best-effort) -> returns a dict with seed/qr if available"""
        data = {"_uuid": self.device.uuid, "_uid": self.user_id}
        try:
            return self.private_request(
                "accounts/account_security_info/", data
            )
        except ClientError:
            return {}

    def enable_totp_two_factor(self, verification_code: str) -> Dict[str, Any]:
        """Confirm the code from the authenticator app to enable TOTP 2FA (best-effort)"""
        data = {
            "verification_code": str(verification_code).replace(" ", ""),
            "_uuid": self.device.uuid,
            "_uid": self.user_id,
        }
        try:
            return self.private_request(
                "accounts/enable_totp_two_factor/", data
            )
        except ClientError:
            return {}

    def disable_totp_two_factor(self) -> Dict[str, Any]:
        """Disable TOTP 2FA (best-effort)"""
        data = {"_uuid": self.device.uuid, "_uid": self.user_id}
        try:
            return self.private_request(
                "accounts/disable_totp_two_factor/", data
            )
        except ClientError:
            return {}

    # ------------------------------------------------------------------
    # Recovery / help
    # ------------------------------------------------------------------
    def send_recovery_flow_email(self, query: str) -> Dict[str, Any]:
        """Request to send an account recovery email to the username/email/phone specified in query"""
        data = {
            "query": query,
            "_uuid": self.device.uuid,
            "device_id": self.device.device_id,
        }
        return self.private_request("accounts/send_recovery_flow_email/", data)

    def send_password_reset(self, username_or_email: str) -> Dict[str, Any]:
        """Request a password reset to the specified username/email"""
        data = {
            "user_email": username_or_email,
            "_uuid": self.device.uuid,
            "device_id": self.device.device_id,
            "guid": self.device.uuid,
        }
        return self.private_request("accounts/send_password_reset/", data)

    # ------------------------------------------------------------------
    # Presence status / notifications (basic settings)
    # ------------------------------------------------------------------
    def set_presence_disabled(self, disabled: bool = True) -> Dict[str, Any]:
        """Enable/disable the online status (activity status) that others can see"""
        data = {
            "_uuid": self.device.uuid,
            "_uid": self.user_id,
            "disabled": "1" if disabled else "0",
        }
        return self.private_request("accounts/set_presence_disabled/", data)

    def set_account_type(self, account_type: int) -> Dict[str, Any]:
        """
        Change the account type (best-effort): 1=personal, 2=business, 3=creator
        Note: business accounts require a separate flow; this is a minimal-effort attempt
        """
        data = {
            "_uuid": self.device.uuid,
            "_uid": self.user_id,
            "account_type": account_type,
        }
        try:
            return self.private_request(
                "business/account/convert_account/", data
            )
        except ClientError:
            return {}

    # ------------------------------------------------------------------
    # Previously logged-in accounts (multiple account)
    # ------------------------------------------------------------------
    def _account_list_page(
        self, max_id: str = ""
    ) -> Dict[str, Any]:
        """A (raw) page of the list of accounts previously logged in on this device — returns a dict"""
        params: Dict[str, Any] = {}
        if max_id:
            params["max_id"] = max_id
        return self.private_request(
            "multiple_accounts/get_account_family/", params=params or None
        )

    def get_account_family(self, amount: int = 0) -> List[Dict[str, Any]]:
        """
        Fetch the list of accounts in the family (linked to the current account) across multiple pages
        amount=0 = fetch all (loop guarded at a maximum of ~50 pages)
        """
        accounts: List[Dict[str, Any]] = []
        max_id = ""
        for _ in range(50):
            data = self._account_list_page(max_id)
            chunk = (
                data.get("accounts")
                or data.get("account_family", [])
            )
            if isinstance(chunk, dict):
                chunk = chunk.get("accounts", [])
            accounts.extend(chunk)
            if amount and len(accounts) >= amount:
                break
            next_max_id = data.get("next_max_id")
            if not next_max_id:
                break
            max_id = str(next_max_id)
        return accounts[:amount] if amount else accounts

    # ------------------------------------------------------------------
    # Delete/temporarily deactivate (best-effort, use with caution)
    # ------------------------------------------------------------------
    def get_profile_completion(self) -> Dict[str, Any]:
        """Fetch the profile completion status (percentage/steps not yet done)"""
        try:
            return self.private_request(
                "users/profile_completion/info/"
            )
        except ClientError:
            return {}
