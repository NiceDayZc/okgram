# -*- coding: utf-8 -*-
"""Account examples — demonstrates every AccountMixin method."""
from _common import get_client, login, section, show, RUN_WRITES, my_user_id, writes_disabled_note

cl = login(get_client())
me = my_user_id(cl)   # the logged-in account's user id

section("Read examples")
# Fetch info for the logged-in account (full editable field set)
res = cl.get_current_user(); show("get_current_user", res)
# Alias of get_current_user — returns the current account info dict
res = cl.account_info(); show("account_info", res)
# Fetch the full JSON of accounts/current_user/ (beyond just the user dict)
res = cl.get_account_settings(); show("get_account_settings", res)
# Fetch the account's security info (2FA status, backup phone/email, etc.)
res = cl.account_security_info(); show("account_security_info", res)
# Fetch the list of accounts linked to the current account (account family)
res = cl.get_account_family(amount=10); show("get_account_family", res)
# Fetch the profile completion status (percentage / pending steps)
res = cl.get_profile_completion(); show("get_profile_completion", res)

section("Write examples (guarded)")
if RUN_WRITES:
    # Edit profile fields in one call (base values overridden by the kwargs given)
    cl.edit_profile(biography="Hello from the API", first_name="Example Name")
    # Set the display name (full name) of the account
    cl.set_name("Example Name")
    # Change the username of the account
    cl.set_username("example_username")
    # Set the bio as raw text
    cl.set_biography("Automated bio via okgram")
    # Set the website link (external url) shown on the profile
    cl.set_external_url("https://example.com")
    # Set the gender (1=male, 2=female, 3=unspecified)
    cl.set_gender(3)
    # Set the phone number on the profile
    cl.set_phone_number("+10000000000")
    # Set the email on the profile
    cl.set_email("you@example.com")
    # Switch the account to private
    cl.account_set_private()
    # Switch the account back to public
    cl.account_set_public()
    # Change the password (old_password, new_password)
    cl.change_password("old_password_here", "new_password_here")
    # Upload an image and set it as the new profile picture
    cl.change_profile_picture("avatar.jpg")
    # Remove the current profile picture
    cl.remove_profile_picture()
    # Request to enable TOTP 2FA (best-effort) — returns seed/qr if available
    cl.request_two_factor_enable()
    # Confirm the authenticator-app code to enable TOTP 2FA
    cl.enable_totp_two_factor("123456")
    # Disable TOTP 2FA
    cl.disable_totp_two_factor()
    # Request an account recovery email for the given username/email/phone
    cl.send_recovery_flow_email("you@example.com")
    # Request a password reset to the given username/email
    cl.send_password_reset("you@example.com")
    # Enable/disable the visible online (activity) status
    cl.set_presence_disabled(True)
    # Change the account type (best-effort): 1=personal, 2=business, 3=creator
    cl.set_account_type(1)
else:
    writes_disabled_note()

print("\nAccount examples done.")
