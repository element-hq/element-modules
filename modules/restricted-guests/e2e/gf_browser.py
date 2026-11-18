#!/usr/bin/env python3
"""The browser journeys of the guest flows run, in headless Chromium against
Element Web built from `florianduros/email-invitation`:

1. email invite: an inviter uses "Invite guests" on a room; the guest follows the
   emailed link, signs up with no password, skips consent, lands on the room and
   asks to join; the inviter approves, and the guest joins
2. open link: the same dialog's invite link; a second guest signs up with a
   display name and no email (#6058), skips consent, lands on the room and asks
   to join
3. consent negatives: an older account, and the first guest's second sign-in
   (from a second Element Web origin), both see the consent screen

Run it with the stack up (stack.sh start).
"""

import os
import re
import subprocess
import sys
import time
from urllib.parse import quote

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from browser import close, launch  # noqa: E402
from gf_common import (  # noqa: E402
    admin,
    admin_token,
    check,
    code_in,
    link_in,
    mails,
    session as api,
    summary,
    wait_mail,
)

HERE = os.path.dirname(os.path.abspath(__file__))
SCREENS = f"{HERE}/screens"
SYNAPSE = "http://localhost:8008"
MAS = "http://localhost:8080"
ELEMENT = "http://localhost:8090"
ELEMENT2 = "http://localhost:8091"
SERVER_NAME = "localhost:8008"
PASSWORD = "gf-password-1"
ROOM_NAME = "Guest room"
GUEST = re.compile(r"@guest-[a-z0-9]{32}:" + re.escape(SERVER_NAME))
TIMEOUT = 60_000
MAX_ACCOUNT_AGE = 120
WEBAPP = os.environ.get("GF_WEBAPP", f"{HERE}/work/webapp")


class Abort(Exception):
    pass


def mx(token, method, path, body=None):
    return api.request(method, f"{SYNAPSE}{path}", json=body, headers={"Authorization": f"Bearer {token}"})


def enc(value):
    return quote(value, safe="")


def new_user(name, password):
    token = admin_token()
    r = admin("POST", "/users", token, json={"username": name})
    if r.status_code != 201:
        raise Abort(f"POST /users {name}: {r.status_code} {r.text}")
    mas_id = r.json()["data"]["id"]
    p = admin("POST", f"/users/{mas_id}/set-password", token, json={"password": password, "skip_password_check": True})
    if p.status_code != 204:
        raise Abort(f"set-password {name}: {p.status_code} {p.text}")
    return mas_id


def personal_token(mas_id, name):
    s = admin(
        "POST",
        "/personal-sessions",
        admin_token(),
        json={
            "actor_user_id": mas_id,
            "human_name": f"gf {name}",
            "scope": f"urn:matrix:client:api:* urn:matrix:client:device:GF{name.upper()}",
        },
    )
    return s.json()["data"]["attributes"]["access_token"]


def members(token, room_id):
    r = mx(token, "GET", f"/_matrix/client/v3/rooms/{enc(room_id)}/state")
    return {ev["state_key"]: ev["content"].get("membership") for ev in r.json() if ev["type"] == "m.room.member"}


def join_rule(token, room_id):
    r = mx(token, "GET", f"/_matrix/client/v3/rooms/{enc(room_id)}/state/m.room.join_rules/")
    return r.json().get("join_rule")


def until(what, fn, timeout=60):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = fn()
        if value:
            return value
        time.sleep(0.5)
    raise Abort(f"timed out after {timeout}s waiting for {what}")


class Steps:
    """One browser's journey: numbered screenshots, and every URL it went through"""

    def __init__(self, page, prefix):
        self.page, self.prefix, self.n, self.trail = page, prefix, 0, []
        # Every response to MAS's consent page: 303 when the policy skipped it,
        # 200 when it was shown
        self.consent = []
        page.on(
            "response",
            lambda r: r.url.startswith(f"{MAS}/consent/") and r.request.method == "GET"
            and self.consent.append(r.status),
        )
        # Where MAS's /register/continue sent the browser
        self.open_room = []
        page.on(
            "response",
            lambda r: r.url.startswith(f"{MAS}/register/continue/") and self.open_room.append((r.status, r.headers.get("location"))),
        )

    def shot(self, label):
        self.n += 1
        path = f"{SCREENS}/{self.prefix}-{self.n:02d}-{label}.png"
        self.page.screenshot(path=path)
        self.trail.append(f"{self.n:02d} {label}: {self.page.url[:110]} -> screens/{os.path.basename(path)}")

    def fail(self, label, e):
        try:
            self.shot(f"failed-{label}")
            body = self.page.locator("body").inner_text(timeout=5000)[:800].replace("\n", " | ")
        except Exception as inner:
            body = f"(no page text: {inner!r})"
        raise Abort(f"{label}: {e!r}\n      page text: {body}\n      steps:\n      " + "\n      ".join(self.trail))

    def __str__(self):
        return "\n      ".join(self.trail)


def visible(locator, timeout=TIMEOUT):
    locator.first.wait_for(state="visible", timeout=timeout)
    return locator.first


def mas_password_login(s, username):
    """On MAS's login page, sign in with a password"""
    visible(s.page.locator("input[name=username]"))
    s.page.fill("input[name=username]", username)
    s.page.fill("input[name=password]", PASSWORD)
    s.shot("mas-login")
    s.page.locator("button[type=submit]").first.click()


def element_sign_in(s, origin=ELEMENT):
    """From a signed-out Element Web, start signing in through MAS. Returns when the
    browser is on MAS."""
    sign_in = s.page.get_by_role("link", name=re.compile(r"^Sign in$")).or_(
        s.page.get_by_role("button", name=re.compile(r"^(Sign in|Continue)$"))
    ).or_(s.page.get_by_text("Sign in here", exact=True))
    visible(sign_in)
    s.shot("element-signed-out")
    sign_in.first.click()
    # Element Web may show its own "Continue" before handing over to MAS. A
    # browser already signed in to MAS, whose consent is skipped, can come back
    # signed in before the URL is seen on MAS.
    if not on_mas_or_signed_in(s.page, 10):
        cont = s.page.get_by_role("button", name=re.compile(r"^Continue$"))
        visible(cont)
        s.shot("element-continue")
        cont.first.click()
        if not on_mas_or_signed_in(s.page, TIMEOUT / 1000):
            raise Abort(f"Element Web never handed over to MAS: at {s.page.url}")


def on_mas_or_signed_in(page, seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if page.url.startswith(MAS):
            return True
        try:
            if page.evaluate("() => !!window.localStorage.getItem('mx_user_id')"):
                return True
        except Exception:
            pass
        time.sleep(0.2)
    return False


def logged_in(page):
    """Wait until Element Web has finished signing in, and return the user ID"""
    page.wait_for_function("() => !!window.localStorage.getItem('mx_user_id')", timeout=TIMEOUT)
    return page.evaluate("() => window.localStorage.getItem('mx_user_id')")


def back_to_element(s, origin=ELEMENT, consent=True):
    """On MAS after Element Web handed over: if the consent screen shows, screenshot
    it and approve it (unless `consent` is False, then stop there). Otherwise wait
    for Element Web to finish signing in. Returns the user ID, or None if stopped
    at consent."""
    target = re.compile(rf"^{re.escape(origin)}/")
    deadline = time.monotonic() + TIMEOUT / 1000
    while time.monotonic() < deadline:
        if target.match(s.page.url):
            return logged_in(s.page)
        if s.page.url.startswith(f"{MAS}/consent/"):
            s.page.get_by_role("button", name=re.compile(r"^Continue$")).first.wait_for(timeout=TIMEOUT)
            s.shot("mas-consent")
            if not consent:
                return None
            s.page.get_by_role("button", name=re.compile(r"^Continue$")).first.click()
            s.page.wait_for_url(target, timeout=TIMEOUT)
            return logged_in(s.page)
        time.sleep(0.3)
    raise Abort(f"never got back to {origin}: at {s.page.url}")


def dismiss_toasts(page):
    for name in ("Dismiss", "Not now", "Later", "OK", "Close"):
        for b in page.get_by_role("button", name=name).all():
            try:
                if b.is_visible():
                    b.click(timeout=2000)
            except Exception:
                pass


def open_invite_dialog(s, room_id):
    """In the inviter's Element Web, open the room's info and its Invite guests dialog"""
    s.page.goto(f"{ELEMENT}/#/room/{room_id}")
    visible(s.page.get_by_text(ROOM_NAME))
    time.sleep(2)
    dismiss_toasts(s.page)
    if not s.page.get_by_role("menuitem", name=re.compile("Invite guests", re.I)).or_(
        s.page.get_by_role("button", name=re.compile("Invite guests", re.I))
    ).count():
        visible(s.page.get_by_role("button", name=re.compile(r"^Room info$"))).click()
    invite = s.page.get_by_role("menuitem", name=re.compile("Invite guests", re.I)).or_(
        s.page.get_by_role("button", name=re.compile("Invite guests", re.I))
    )
    visible(invite)
    s.shot("room-info")
    invite.first.click()
    dialog = visible(s.page.get_by_role("dialog"))
    time.sleep(1)
    return dialog


def capture_links(page):
    """The responses to the dialog's invite link requests"""
    links = []

    def on_response(r):
        if r.url.endswith("/_synapse/client/invite_guests/link") and r.request.method == "POST":
            try:
                links.append((r.status, r.json()))
            except Exception:
                links.append((r.status, None))

    page.on("response", on_response)
    return links


def inviter_signs_in(context):
    s = Steps(context.new_page(), "1-inviter")
    links = capture_links(s.page)
    try:
        s.page.goto(ELEMENT)
        element_sign_in(s)
        mas_password_login(s, "ina")
        back_to_element(s)
    except Abort:
        raise
    except Exception as e:
        s.fail("inviter sign-in", e)
    return s, links


def inviter_invites(s, room_id, address):
    """Invite `address` with the dialog, switching the room to Ask to join"""
    try:
        dialog = open_invite_dialog(s, room_id)
        s.shot("invite-dialog")
        text = dialog.inner_text()
        checkbox = dialog.get_by_role("checkbox")
        if checkbox.count():
            checkbox.first.check()
        email_input = dialog.get_by_placeholder(re.compile("email", re.I))
        email_input.fill(address)
        email_input.press("Enter")
        s.shot("invite-dialog-filled")
        send = dialog.get_by_role("button", name=re.compile(r"^Send invite"))
        visible(send).click()
        success = visible(s.page.get_by_role("dialog"))
        visible(success.get_by_text(address))
        s.shot("invite-sent")
        success_text = success.inner_text()
        dismiss = success.get_by_role("button", name=re.compile(r"^(Done|Close|OK)$"))
        if dismiss.count():
            dismiss.first.click()
        else:
            s.page.keyboard.press("Escape")
        return text, success_text
    except Abort:
        raise
    except Exception as e:
        s.fail("inviter invites", e)


def inviter_copies_link(s, room_id, links):
    """Reopen the dialog, now that the room is Ask to join, and take its invite link"""
    try:
        before = len(links)
        dialog = open_invite_dialog(s, room_id)
        copy = dialog.get_by_role("button", name=re.compile("Copy invite link", re.I))
        visible(copy)
        s.shot("invite-dialog-with-link")
        until("the dialog's invite link request", lambda: len(links) > before, timeout=10)
        status, body = links[-1]
        s.page.keyboard.press("Escape")
        return status, body
    except Abort:
        raise
    except Exception as e:
        s.fail("inviter copies link", e)


def mas_register(s, email_to_enter, seen, display_name=None):
    """On MAS's register page from an invite link: enter the email if asked,
    continue, take the code from the mail sink, give a display name. A link
    without an email asks for the display name first and sends no code. Returns
    what the page offered."""
    page = s.page
    submit = page.get_by_role("button", name=re.compile(r"^(Send code|Continue|Create Account)$"))
    visible(submit)
    time.sleep(1)
    email_field = page.locator("input[type=email]:visible, input[name=email]:visible")
    name_field = page.locator("input[name=display_name]:visible")
    shape = {
        "page text": page.locator("main, body").first.inner_text()[:300].replace("\n", " | "),
        "submit": submit.first.inner_text(),
        "password inputs": page.locator("input[type=password]").count(),
        "username inputs": page.locator("input[name=username]:visible").count(),
        "email field": email_field.count(),
        "email editable": email_field.count() > 0 and email_field.first.is_editable(),
        "provider buttons": page.locator("a[href*='/upstream/authorize'], button[name=provider]").count(),
        "display name field": name_field.count(),
    }
    s.shot("mas-register")
    if shape["display name field"] and not shape["email field"]:
        name_field.first.fill(display_name)
        submit.first.click()
        return shape
    if email_to_enter:
        email_field.first.fill(email_to_enter)
    submit.first.click()
    visible(page.locator("input[name=code]"))
    s.shot("mas-verify-email")
    address = email_to_enter or re.search(r"[\w.+-]+@[\w.-]+", shape["page text"]).group(0)
    m = wait_mail(address, seen, subject_re="code|verif|Verif")
    if not m:
        raise Abort(f"no verification email for {address}")
    seen.add(m["key"])
    code = code_in(m["subject"] + " " + m["text"])
    page.fill("input[name=code]", code)
    page.locator("button[type=submit]").first.click()
    try:
        page.locator("input[name=display_name]").wait_for(timeout=15_000)
        page.fill("input[name=display_name]", f"Guest {address.split('@')[0]}")
        s.shot("mas-display-name")
        page.locator("button[type=submit]").first.click()
    except Exception:
        pass
    return shape


def guest_to_room(s):
    """After registering: MAS sends the browser to the room in Element Web, which
    is signed out; sign in through MAS (already signed in there) and wait for the
    room's Ask to join. Returns the user ID."""
    s.page.wait_for_url(re.compile(rf"^{re.escape(ELEMENT)}/"), timeout=TIMEOUT)
    landed = s.open_room[-1][1] if s.open_room else None
    time.sleep(2)
    s.shot("element-landing")
    element_sign_in(s)
    user_id = back_to_element(s, consent=False)
    if user_id is None:
        raise Abort(f"the consent screen was shown (consent responses {s.consent})")
    visible(s.page.get_by_role("button", name=re.compile(r"^Request to join$")))
    s.shot("ask-to-join")
    return landed, user_id


def knock(s, ina, room_id, user_id):
    s.page.get_by_role("button", name=re.compile(r"^Request to join$")).first.click()
    until(f"{user_id}'s knock", lambda: members(ina, room_id).get(user_id) == "knock")
    time.sleep(1)
    s.shot("request-sent")


def email_guest(context, room_id, ina, seen):
    s = Steps(context.new_page(), "2-email-guest")
    try:
        m = wait_mail("guest1@example.com", seen, subject_re="invited")
        if not m:
            raise Abort("no invite email for guest1@example.com")
        seen.add(m["key"])
        link = link_in(m["text"])
        s.page.goto(link)
        shape = mas_register(s, None, seen)
        shape["link"] = link
        landed, user_id = guest_to_room(s)
        knock(s, ina, room_id, user_id)
        return s, m, shape, landed, user_id
    except Abort:
        raise
    except Exception as e:
        s.fail("email guest", e)


def approve(s_ina, room_id, guest_id):
    """The inviter approves the knock in Element Web"""
    try:
        s_ina.page.goto(f"{ELEMENT}/#/room/{room_id}")
        approve = s_ina.page.get_by_role("button", name=re.compile(r"^Approve$"))
        visible(approve)
        s_ina.shot("knock-request")
        approve.first.click()
        time.sleep(2)
        s_ina.shot("approved")
    except Exception as e:
        s_ina.fail("approve", e)


def guest_joins(s, ina, room_id, guest_id):
    """After approval, the guest's Element Web joins the room itself, or shows
    the invite; accept it"""
    try:
        until(f"{guest_id} invited", lambda: members(ina, room_id).get(guest_id) in ("invite", "join"))
        try:
            until(f"{guest_id} joined by Element Web", lambda: members(ina, room_id).get(guest_id) == "join", timeout=15)
        except Abort:
            accept = s.page.get_by_role("button", name=re.compile(r"^(Accept|Join)$"))
            visible(accept)
            s.shot("invited")
            accept.first.click()
        until(f"{guest_id} joined", lambda: members(ina, room_id).get(guest_id) == "join")
        time.sleep(2)
        s.shot("joined")
    except Abort:
        raise
    except Exception as e:
        s.fail("guest joins", e)


def link_guest(context, room_id, ina, link, seen):
    s = Steps(context.new_page(), "3-link-guest")
    try:
        s.page.goto(link)
        shape = mas_register(s, None, seen, display_name="Guest link")
        landed, user_id = guest_to_room(s)
        knock(s, ina, room_id, user_id)
        return s, shape, landed, user_id
    except Abort:
        raise
    except Exception as e:
        s.fail("link guest", e)


def second_sign_in(context):
    """The email guest, still signed in to MAS, signs in to a second Element Web"""
    s = Steps(context.new_page(), "4-guest-second-sign-in")
    try:
        s.page.goto(ELEMENT2)
        element_sign_in(s, ELEMENT2)
        back_to_element(s, ELEMENT2, consent=False)
        return s
    except Abort:
        raise
    except Exception as e:
        s.fail("second sign-in", e)


def older_account(context):
    s = Steps(context.new_page(), "5-older-account")
    try:
        s.page.goto(ELEMENT)
        element_sign_in(s)
        mas_password_login(s, "olga")
        back_to_element(s, consent=False)
        return s
    except Abort:
        raise
    except Exception as e:
        s.fail("older account", e)


def main():
    os.makedirs(SCREENS, exist_ok=True)
    for old in os.listdir(SCREENS):
        os.remove(f"{SCREENS}/{old}")
    seen = {m["key"] for m in mails()}

    olga_created = time.monotonic()
    new_user("olga", PASSWORD)
    ina_id = new_user("ina", PASSWORD)
    ina = personal_token(ina_id, "ina")
    room_id = mx(ina, "POST", "/_matrix/client/v3/createRoom", {"name": ROOM_NAME, "preset": "private_chat"}).json()["room_id"]
    print(f"room {room_id}", flush=True)

    # A second Element Web origin, for the guest's second sign-in
    second = subprocess.Popen(
        [sys.executable, f"{HERE}/element_serve.py", WEBAPP, f"{HERE}/config/element-config.json", "8091"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    pw, browser, ina_ctx = launch(bypass_csp=True)
    try:
        # 1. Email invite
        try:
            s_ina, links = inviter_signs_in(ina_ctx)
            check("inviter signs in to Element Web through MAS", True, f"steps:\n      {s_ina}")
            before_dialog, success = inviter_invites(s_ina, room_id, "guest1@example.com")
            check(
                "Invite guests: the dialog offers to switch the room to Ask to join, and sends the invite",
                "Ask to join" in before_dialog and join_rule(ina, room_id) == "knock" and "guest1@example.com" in success,
                f"join rule now {join_rule(ina, room_id)}; first dialog link request {links[:1]}; steps:\n      {s_ina}",
            )
            m = wait_mail("guest1@example.com", seen, subject_re="invited", timeout=30)
            check("the invite email reaches the mail sink", m is not None, m and m["subject"])
            if m:
                first = m["text"].strip().splitlines()[0]
                check(
                    "invite email: subject, headline with the room and the inviter, approval line",
                    m["subject"] == "You have been invited to a room on localhost:8008"
                    and first == f"ina (@ina:{SERVER_NAME}) invited you to ask to join {ROOM_NAME} on {SERVER_NAME}. Someone in the room will approve your request.",
                    f"subject {m['subject']!r}; first line {first!r}",
                )
            g_ctx = browser.new_context(bypass_csp=True)
            s_g, m, shape, landed, guest_id = email_guest(g_ctx, room_id, ina, seen)
            check(
                "email guest: MAS's register page shows the pinned address with no email, password or username field, "
                "and no providers",
                shape["password inputs"] == 0 and shape["username inputs"] == 0 and shape["email field"] == 0
                and "guest1@example.com" in shape["page text"] and shape["provider buttons"] == 0
                and shape["submit"] == "Send code",
                f"{shape}",
            )
            check(
                "email guest: registered as a guest-<random> localpart, sent to the room in Element Web",
                GUEST.fullmatch(guest_id) and landed == f"{ELEMENT}/#/room/{enc(room_id)}",
                f"{guest_id}; MAS's /register/continue redirect: {s_g.open_room}",
            )
            check(
                "email guest: consent skipped (MAS answered /consent with a redirect, not the page)",
                s_g.consent and all(st == 303 for st in s_g.consent),
                f"consent responses {s_g.consent}",
            )
            check("email guest: Ask to join, and Request to join knocks", members(ina, room_id).get(guest_id) == "knock", f"steps:\n      {s_g}")
            approve(s_ina, room_id, guest_id)
            guest_joins(s_g, ina, room_id, guest_id)
            check("inviter approves in Element Web, and the guest joins", members(ina, room_id).get(guest_id) == "join", f"steps:\n      {s_ina}\n      {s_g}")
        except Abort as e:
            check("email invite journey ran to the end", False, str(e))
            g_ctx = None

        # 2. Open link
        try:
            status, body = inviter_copies_link(s_ina, room_id, links)
            link = (body or {}).get("invite_url")
            check("the dialog fetches an invite link once the room is Ask to join", status == 200 and link, f"{status} {body}")
            l_ctx = browser.new_context(bypass_csp=True)
            s_l, shape, landed, link_guest_id = link_guest(l_ctx, room_id, ina, link, seen)
            check(
                "link guest: MAS's register page asks for a display name, with no email, password or username field",
                shape["password inputs"] == 0 and shape["username inputs"] == 0 and shape["email field"] == 0
                and shape["display name field"] == 1 and shape["submit"] == "Continue",
                f"{shape}",
            )
            check(
                "link guest: registered as a guest-<random> localpart, sent to the room in Element Web",
                GUEST.fullmatch(link_guest_id) and landed == f"{ELEMENT}/#/room/{enc(room_id)}",
                f"{link_guest_id}; MAS's /register/continue redirect: {s_l.open_room}",
            )
            check(
                "link guest: consent skipped",
                s_l.consent and all(st == 303 for st in s_l.consent),
                f"consent responses {s_l.consent}",
            )
            check("link guest: Ask to join, and Request to join knocks", members(ina, room_id).get(link_guest_id) == "knock", f"steps:\n      {s_l}")
        except Abort as e:
            check("open link journey ran to the end", False, str(e))

        # 3. Consent negatives
        try:
            if g_ctx is None:
                raise Abort("no email guest to sign in again")
            s2 = second_sign_in(g_ctx)
            check(
                "email guest's second sign-in (another Element Web, with a session already): consent shown",
                s2.consent and s2.consent[-1] == 200,
                f"consent responses {s2.consent}; steps:\n      {s2}",
            )
        except Abort as e:
            check("second sign-in ran to the end", False, str(e))
        try:
            wait = MAX_ACCOUNT_AGE + 5 - (time.monotonic() - olga_created)
            if wait > 0:
                print(f"waiting {wait:.0f}s for olga's account to be older than {MAX_ACCOUNT_AGE}s", flush=True)
                time.sleep(wait)
            o_ctx = browser.new_context(bypass_csp=True)
            s_o = older_account(o_ctx)
            check(
                f"an account older than {MAX_ACCOUNT_AGE}s signing in for the first time: consent shown",
                s_o.consent and s_o.consent[-1] == 200,
                f"consent responses {s_o.consent}; steps:\n      {s_o}",
            )
        except Abort as e:
            check("older account sign-in ran to the end", False, str(e))
    finally:
        close(pw, browser)
        second.terminate()
    return summary()


if __name__ == "__main__":
    sys.exit(main())
