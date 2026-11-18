"""The admin API checks of the guest flows run: minting registration tokens and
emailing their invite links. Needs the stack up (stack.sh start)."""

import sys

from gf_common import MAS, admin, admin_token, check, link_in, mails, session, summary, wait_mail

token = admin_token()


def mint(**body):
    r = admin("POST", "/user-registration-tokens", token, json=body)
    return r


def send(**body):
    return admin("POST", "/user-registration-tokens/invite-emails", token, json=body)


def title(r):
    try:
        return r.json()["errors"][0]["title"]
    except Exception:
        return r.text[:200]


seen = {m["key"] for m in mails()}

# A token with no room and a pinned address: the email has the no-room wording
r = mint(email="noroom@example.com", username="guest-{{ random }}", passwordless=True, usage_limit=1)
check("API: mint a roomless token pinned to an address (201)", r.status_code == 201, f"{r.status_code}")
noroom = r.json()["data"]
r = send(invites=[{"registration_token_id": noroom["id"]}], inviter="@inviter:localhost:8008", inviter_name="Ina")
check("API: send a roomless pinned token (202, scheduled 1)", r.status_code == 202 and r.json() == {"scheduled": 1}, f"{r.status_code} {r.text}")
m = wait_mail("noroom@example.com", seen)
check("API: roomless email delivered to the pinned address", m is not None)
if m:
    seen.add(m["key"])
    check(
        "API: roomless email subject has no room",
        m["subject"] == "You have been invited to localhost:8008",
        repr(m["subject"]),
    )
    first = m["text"].strip().splitlines()[0] if m["text"].strip() else ""
    check(
        "API: roomless email headline names the inviter and the server, no room",
        first == "Ina (@inviter:localhost:8008) invited you to join localhost:8008.",
        repr(first),
    )
    check("API: roomless email has no approval line", "approve" not in m["text"] and "approve" not in m["html"])
    check("API: roomless email links to the token", link_in(m["text"]) == noroom["attributes"]["invite_url"], f"{link_in(m['text'])} vs {noroom['attributes']['invite_url']}")

# An unpinned token goes to the address given
r = mint(username="guest-{{ random }}", passwordless=True)
unpinned = r.json()["data"]
r = send(invites=[{"registration_token_id": unpinned["id"], "email": "Explicit@Example.com"}])
check("API: send an unpinned token to a given address (202)", r.status_code == 202 and r.json() == {"scheduled": 1}, f"{r.status_code} {r.text}")
m = wait_mail("explicit@example.com", seen)
check("API: unpinned token's email delivered to the given address", m is not None and "Explicit@Example.com" in m["to"], m and m["to"])
if m:
    seen.add(m["key"])

# Refusals
r = send(invites=[{"registration_token_id": noroom["id"], "email": "someone-else@example.com"}])
check("API: an address that isn't the token's is refused (400)", r.status_code == 400, f"{r.status_code} {title(r)}")
r = send(invites=[{"registration_token_id": "01J00000000000000000000000"}])
check("API: an unknown token is 404", r.status_code == 404, f"{r.status_code} {title(r)}")
r = send(invites=[{"registration_token_id": unpinned["id"]}])
check("API: an unpinned token without an address is refused (400)", r.status_code == 400, f"{r.status_code} {title(r)}")
r = mint(email="guest@banned.example", username="guest-{{ random }}", passwordless=True)
check("API: a mint pinning an address the policy refuses is 400", r.status_code == 400, f"{r.status_code} {title(r)}")
check("API: a template is stored as sent", unpinned["attributes"]["username"] == "guest-{{ random }}", unpinned["attributes"]["username"])
for username, why in [
    ("guest-{random}", "the old {random} syntax"),
    ("guest-{{ random", "a template syntax error"),
    ("guest-{{ email }}", "an unknown template variable"),
]:
    r = mint(username=username)
    check(f"API: a mint with {why} is 400", r.status_code == 400, f"{r.status_code} {title(r)}")
r = mint(email="not-an-email")
check("API: a mint with an address that doesn't parse is 400", r.status_code == 400, f"{r.status_code} {title(r)}")

# The continue URL: kept as given, web URLs only, and redirected to without a session
url = "https://client.example/#/room/%21abc%3Aexample.org?via=example.org"
r = mint(continue_url=url)
check("API: a mint keeps its continue_url as given (201)", r.status_code == 201 and r.json()["data"]["attributes"]["continue_url"] == url, f"{r.status_code} {r.text[:200]}")
if r.status_code == 201:
    r2 = session.get(f"{MAS}/register/continue/{r.json()['data']['id']}", allow_redirects=False)
    check("API: /register/continue/{id} redirects to the continue_url, with no session", r2.status_code == 303 and r2.headers.get("location") == url, f"{r2.status_code} {r2.headers.get('location')}")
r2 = session.get(f"{MAS}/register/continue/{unpinned['id']}", allow_redirects=False)
check("API: /register/continue/{id} for a token without a continue_url goes to /", r2.status_code == 303 and r2.headers.get("location") == "/", f"{r2.status_code} {r2.headers.get('location')}")
for bad, why in [
    ("matrix:roomid/abc:example.org", "a matrix: URI"),
    ("javascript:alert(1)", "a javascript: URI"),
    ("client.example/#/room/x", "no scheme"),
    ("https://client.example/#/room/a b", "a space"),
]:
    r = mint(continue_url=bad)
    check(f"API: a mint with a continue_url that is {why} is 400", r.status_code == 400, f"{r.status_code} {title(r)}")
r = mint(room_id="!abc:example.org")
check("API: a mint ignores room_id: MAS has no rooms", r.status_code == 201 and "room_id" not in r.json()["data"]["attributes"], f"{r.status_code} {r.text[:200]}")

# A room name needs nothing of the token: the email names the room
r = mint(email="named@example.com", username="guest-{{ random }}", passwordless=True, usage_limit=1)
named = r.json()["data"]
r = send(invites=[{"registration_token_id": named["id"]}], room_name="Project X")
check("API: room_name is accepted for a token without a continue_url (202)", r.status_code == 202, f"{r.status_code} {title(r)}")
m = wait_mail("named@example.com", seen)
first = m["text"].strip().splitlines()[0] if m and m["text"].strip() else ""
check(
    "API: that email names the room and says someone will approve",
    first == "You have been invited to ask to join Project X on localhost:8008. Someone in the room will approve your request.",
    repr(first),
)

sys.exit(summary())
