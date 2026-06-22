# -*- coding: utf-8 -*-
"""
21 - Hardcore layer: rate governor, egress guard, fingerprint proof, vault.

All four are opt-in and safe to demo offline (the fingerprint/egress parts touch
the network only if you have a connection). No account writes happen here.
"""
import os
import tempfile

from _common import section, show
from okgram import InstagramAPI, RateGovernor, SessionStore
from okgram.exceptions import RateLimitReached


# ---------------------------------------------------------------------------
section("1) Rate governor - human-like caps that stop action blocks")
gov = RateGovernor(think_time=None, mode="raise", limits={"like": (3, 200)})
for i in range(3):
    gov.gate(f"media/{i}/like/")            # 3 likes allowed this hour
show("likes used this hour", gov.counts("like")[0])
try:
    gov.gate("media/99/like/")
except RateLimitReached as e:
    show("4th like blocked", str(e))
show("reads are never gated (timeline)", gov.classify("feed/timeline/"))

# attach to a client so write methods are paced automatically:
cl = InstagramAPI(device_seed="demo", govern=True, auto_geo=False)
show("client.governor active", cl.governor is not None)


# ---------------------------------------------------------------------------
section("2) Egress guard + smart retry")
# guard_egress compares the egress IP region to the session region (needs net).
try:
    rep = cl.guard_egress(policy="warn")
    show("egress report", rep)
except Exception as e:  # noqa
    show("egress (offline)", repr(e))

from okgram import guard
class _Resp:  # show Retry-After awareness without a real 429
    headers = {"Retry-After": "8"}
class _Exc(Exception):
    response = _Resp()
show("retry waits per IG's Retry-After", round(guard.retry_wait(_Exc(), 0), 2))


# ---------------------------------------------------------------------------
section("3) Fingerprint proof - what actually leaves the socket")
fp = cl.fingerprint()
show("engine", fp.get("engine"))
show("verdict", fp.get("verdict"))
if fp.get("fingerprint"):
    show("JA3 hash", fp["fingerprint"].get("ja3_hash"))
    show("HTTP/2 akamai", fp["fingerprint"].get("akamai"))


# ---------------------------------------------------------------------------
section("4) Multi-account vault - proxy per account, encrypted at rest")
vault_dir = tempfile.mkdtemp()
vault = SessionStore(vault_dir, password="demo-pass")     # AES-GCM at rest

# seed two accounts (no network: verify=False under the hood via dict bundles)
a = InstagramAPI(device_seed="acctA", auto_geo=False)
a.user_id, a.username, a.ig_u_rur = "111", "alice", "RUR-A"
vault.add("alice", a, proxy="http://u:p@proxyA:8080")

b = InstagramAPI(device_seed="acctB", auto_geo=False)
b.user_id, b.username = "222", "bob"
vault.add("bob", b, proxy="socks5://proxyB:1080")

show("accounts", vault.list())
for name in vault.list():
    show(name, vault.info(name))          # proxy is masked, secrets hidden

opened = vault.open("alice")
show("reopened alice device stable", opened.device.uuid == a.device.uuid)
show("reopened alice proxy bound", getattr(opened, "proxy", None))
show("reopened alice rur restored", opened.ig_u_rur)

print("\nCLI:  okgram accounts add alice '<sessionid>' --proxy ... --store ./vault --password ...")
print("CLI:  okgram fingerprint --session acct.json   |   okgram doctor --online")
