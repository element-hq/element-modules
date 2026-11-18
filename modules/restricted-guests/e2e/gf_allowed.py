#!/usr/bin/env python3
"""The allowed-addresses journeys of the guest flows run:
links from `invite_guests/link` listing the addresses allowed to use them, in
headless Chromium against Element Web, plus checks on the link API.

1. a listed participant signs up through the link and reaches the room
2. an unlisted address is refused on the guest form, and no code is sent
3. a guest signed in with a listed address goes straight to another link's room
4. an email-less guest from an open link, still signed in, goes straight to a
   listed link's room: the list holds sign-ups only
5. the list is replaced: a newly listed address signs up, a dropped one is refused
6. a participant taken off the list stays joined, and their address is refused

The inviter works through the API. Run it with the stack up, after gf_browser.py
(stack.sh run).
"""

import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gf_browser as b  # noqa: E402
from browser import close, launch  # noqa: E402
from gf_common import admin, admin_token, check, mails, summary, wait_mail  # noqa: E402

LINK = f"{b.SYNAPSE}/_synapse/client/invite_guests/link"
NOT_INVITED = "This invite isn't for this email address. Use the address you were invited with."
P1, P2, P3, P4 = (f"p{n}@example.com" for n in range(1, 5))
STRANGER = "stranger@example.com"


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def make_link(token, room_id, emails=None):
    body = {"room_id": room_id}
    if emails is not None:
        body["emails"] = emails
    return b.api.post(LINK, json=body, headers=auth(token))


def put_link(token, link_id, room_id, emails):
    body = {"emails": emails}
    if room_id is not None:
        body["room_id"] = room_id
    return b.api.put(f"{LINK}/{link_id}", json=body, headers=auth(token))


def mas_token(link_id):
    r = admin("GET", f"/user-registration-tokens/{link_id}", admin_token())
    return r.status_code, r.json().get("data", {}).get("attributes", {})


def listed(link_id):
    return sorted(e.lower() for e in (mas_token(link_id)[1].get("allowed_emails") or []))


def mas_user_id(user_id):
    localpart = user_id[1:].split(":")[0]
    return admin("GET", f"/users/by-username/{localpart}", admin_token()).json()["data"]["id"]


def user_emails(user_id):
    r = admin("GET", "/user-emails", admin_token(), params={"filter[user]": mas_user_id(user_id)})
    return [e["attributes"]["email"] for e in r.json()["data"]]


def mails_to(address):
    return [m for m in mails() if address.lower() in m["to"].lower()]


def knock_room(token, name):
    room_id = b.mx(token, "POST", "/_matrix/client/v3/createRoom", {"name": name, "preset": "private_chat"}).json()["room_id"]
    b.mx(token, "PUT", f"/_matrix/client/v3/rooms/{b.enc(room_id)}/state/m.room.join_rules/", {"join_rule": "knock"})
    return room_id


def names_none(html, addresses):
    """The listed addresses that appear in `html`"""
    return [a for a in addresses if a.lower() in html.lower()]


def room_url(room_id):
    return f"{b.ELEMENT}/#/room/{b.enc(room_id)}"


def mas_trail(s):
    """Record every MAS response the page gets, as (status, path)"""
    s.mas = []
    s.page.on(
        "response",
        lambda r: r.url.startswith(b.MAS) and r.request.resource_type == "document"
        and s.mas.append((r.status, r.url[len(b.MAS):][:80])),
    )
    return s


def steps(ctx, prefix):
    return mas_trail(b.Steps(ctx.new_page(), prefix))


def sign_up(ctx, prefix, link, email, seen, display_name=None):
    """A fresh browser signs up through `link` with `email` (or, on a link without
    an email, a display name), lands on the room in Element Web and signs in"""
    s = steps(ctx, prefix)
    try:
        s.page.goto(link)
        b.visible(s.page.get_by_role("button", name=re.compile(r"^(Send code|Continue)$")))
        html = s.page.content()
        shape = b.mas_register(s, email, seen, display_name=display_name)
        landed, user_id = b.guest_to_room(s)
        return s, shape, html, landed, user_id
    except b.Abort:
        raise
    except Exception as e:
        s.fail(prefix, e)


def refused(ctx, prefix, link, email, seen):
    """A fresh browser tries to sign up through `link` with `email`, which the
    link doesn't list. Returns what the page showed and any mail sent."""
    s = steps(ctx, prefix)
    try:
        s.page.goto(link)
        page = s.page
        submit = b.visible(page.get_by_role("button", name=re.compile(r"^Send code$")))
        time.sleep(1)
        page.locator("input[name=email]:visible").first.fill(email)
        s.shot("mas-register")
        submit.click()
        error = b.visible(page.get_by_text(NOT_INVITED))
        time.sleep(1)
        s.shot("refused")
        result = {
            "error": error.inner_text(),
            "url": page.url[len(b.MAS):],
            "code inputs": page.locator("input[name=code]").count(),
            "MAS responses": s.mas,
        }
        html = page.content()
        m = wait_mail(email, seen, timeout=10)
        result["mail"] = m and m["subject"]
        return s, result, html
    except b.Abort:
        raise
    except Exception as e:
        s.fail(prefix, e)


def to_room(s, link, label):
    """A browser signed in to MAS and Element Web opens `link` and lands on its
    room in Element Web, at Request to join. Returns the MAS responses on the
    way, where /register/continue sent it, and who Element Web is signed in as."""
    try:
        before, opened = len(s.mas), len(s.open_room)
        s.page.goto(link)
        s.page.wait_for_url(re.compile(rf"^{re.escape(b.ELEMENT)}/#/room/"), timeout=b.TIMEOUT)
        b.visible(s.page.get_by_role("button", name=re.compile(r"^Request to join$")))
        s.shot(label)
        landed = s.open_room[-1][1] if len(s.open_room) > opened else None
        return s.mas[before:], landed, s.page.evaluate("() => window.localStorage.getItem('mx_user_id')")
    except b.Abort:
        raise
    except Exception as e:
        s.fail(label, e)


def joined(s, ivy, room_id, user_id):
    b.mx(ivy, "POST", f"/_matrix/client/v3/rooms/{b.enc(room_id)}/invite", {"user_id": user_id})
    b.guest_joins(s, ivy, room_id, user_id)


def main():
    for old in os.listdir(b.SCREENS):
        if old.startswith("a"):
            os.remove(f"{b.SCREENS}/{old}")
    seen = {m["key"] for m in mails()}

    ivy = b.personal_token(b.new_user("ivy", b.PASSWORD), "ivy")
    nora = b.personal_token(b.new_user("nora", b.PASSWORD), "nora")
    room_a = knock_room(ivy, "Meeting room")
    room_b = knock_room(ivy, "Second room")
    print(f"room A {room_a}, room B {room_b}", flush=True)

    # The links. L1 lists the meeting's participants, L2 lists P1 for room B,
    # and L0 is an open link to room B.
    r = make_link(ivy, room_a, [P1, "P2@Example.com", P3, "P1@EXAMPLE.COM"])
    l1 = r.json()
    status, token = mas_token(l1.get("id"))
    check(
        "allowed API: POST link with emails is 200 with the token's id and invite_url, and MAS holds the list, "
        "deduplicated ignoring case",
        r.status_code == 200 and set(l1) == {"id", "invite_url"} and status == 200
        and token.get("invite_url") == l1["invite_url"]
        and sorted(e.lower() for e in token.get("allowed_emails") or []) == [P1, P2, P3],
        f"{r.status_code} {l1}; MAS token {status}: allowed_emails {token.get('allowed_emails')}, "
        f"username {token.get('username')!r}, room {token.get('room_id')}",
    )
    r = make_link(ivy, room_b)
    l0 = r.json()
    status, token = mas_token(l0.get("id"))
    check(
        "allowed API: POST link without emails is 200 with an id, and MAS holds no list",
        r.status_code == 200 and set(l0) == {"id", "invite_url"} and status == 200 and token.get("allowed_emails") is None,
        f"{r.status_code} {l0}; MAS token {status}: allowed_emails {token.get('allowed_emails')}",
    )
    r = make_link(ivy, room_b, ["P1@EXAMPLE.COM", "someone@example.com"])
    l2, l2_status = r.json(), r.status_code
    print(f"L2 {l2_status} {l2}", flush=True)

    pw, browser, ctx = launch(bypass_csp=True)
    try:
        # 1. A listed participant
        s1 = p1 = None
        try:
            s1, shape, html, landed, p1 = sign_up(ctx, "a1-listed", l1["invite_url"], P1, seen)
            check(
                "allowed 1: a listed link's register page asks for an email and sends a code, with no password, "
                "username or display name field, no providers, and no listed address",
                shape["email field"] == 1 and shape["email editable"] and shape["submit"] == "Send code"
                and shape["password inputs"] == 0 and shape["username inputs"] == 0
                and shape["display name field"] == 0 and shape["provider buttons"] == 0
                and not names_none(html, [P1, P2, P3]),
                f"{shape}; listed addresses on the page: {names_none(html, [P1, P2, P3])}",
            )
            check(
                "allowed 1: the listed participant registers as a guest-<random> localpart and /register/continue sends them "
                "to the room",
                b.GUEST.fullmatch(p1) and landed == room_url(room_a) and user_emails(p1) == [P1],
                f"{p1}, emails {user_emails(p1)}; /register/continue: {s1.open_room}; consent {s1.consent}",
            )
            b.knock(s1, ivy, room_a, p1)
            joined(s1, ivy, room_a, p1)
            check(
                "allowed 1: the participant asks to join, is approved and joins",
                b.members(ivy, room_a).get(p1) == "join",
                f"membership {b.members(ivy, room_a).get(p1)}; steps:\n      {s1}",
            )
        except b.Abort as e:
            check("allowed 1 ran to the end", False, str(e))

        # 2. An unlisted address
        try:
            s2, result, html = refused(browser.new_context(bypass_csp=True), "a2-unlisted", l1["invite_url"], STRANGER, seen)
            check(
                "allowed 2: an unlisted address gets the field error on the guest form, with no code sent, and the "
                "page names no listed address",
                result["error"] == NOT_INVITED and result["code inputs"] == 0 and result["mail"] is None
                and not mails_to(STRANGER) and not names_none(html, [P1, P2, P3]),
                f"{result}; listed addresses on the page: {names_none(html, [P1, P2, P3])}; steps:\n      {s2}",
            )
        except b.Abort as e:
            check("allowed 2 ran to the end", False, str(e))

        # 3. A guest signed in with a listed address opens another link
        try:
            if s1 is None:
                raise b.Abort("no listed participant")
            trail, landed, user_id = to_room(s1, l2["invite_url"], "other-link-room")
            check(
                "allowed 3: a guest signed in with an address the link lists (in another case) goes straight to its "
                "room, with no sign-up",
                l2_status == 200 and landed == room_url(room_b) and user_id == p1
                and (303, f"/register/continue/{l2['id']}") in trail
                and not any("/register/steps" in p for _, p in trail),
                f"L2 lists {listed(l2['id'])}; MAS responses {trail}; /register/continue sent it to {landed}; "
                f"Element Web signed in as {user_id}",
            )
        except b.Abort as e:
            check("allowed 3 ran to the end", False, str(e))

        # 4. An email-less guest from an open link
        try:
            c4 = browser.new_context(bypass_csp=True)
            s4, shape, html, landed, g4 = sign_up(c4, "a4-emailless", l0["invite_url"], None, seen, display_name="Guest emailless")
            check(
                "allowed 4: a guest signs up through an open link with a display name and no email",
                shape["display name field"] == 1 and shape["email field"] == 0 and b.GUEST.fullmatch(g4)
                and landed == room_url(room_b) and user_emails(g4) == [],
                f"{g4}, emails {user_emails(g4)}; /register/continue: {s4.open_room}",
            )
            trail, landed, user_id = to_room(s4, l1["invite_url"], "listed-room")
            b.knock(s4, ivy, room_a, g4)
            check(
                "allowed 4: signed in, they open the listed link, go straight to its room with no sign-up, and ask "
                "to join",
                landed == room_url(room_a) and user_id == g4 and (303, f"/register/continue/{l1['id']}") in trail
                and not any("/register/steps" in p for _, p in trail)
                and b.members(ivy, room_a).get(g4) == "knock",
                f"MAS responses {trail}; /register/continue sent it to {landed}; membership {b.members(ivy, room_a).get(g4)}; "
                f"steps:\n      {s4}",
            )
        except b.Abort as e:
            check("allowed 4 ran to the end", False, str(e))

        # 5. The list is replaced
        try:
            r = put_link(ivy, l1["id"], room_a, [P1, P2, P4])
            check(
                "allowed 5: PUT link/{id} by the inviter replaces the list: 200 with the same id and invite_url",
                r.status_code == 200 and r.json() == l1 and listed(l1["id"]) == [P1, P2, P4],
                f"{r.status_code} {r.text}; MAS list now {listed(l1['id'])}",
            )
            s5, shape, html, landed, p4 = sign_up(browser.new_context(bypass_csp=True), "a5-newly-listed", l1["invite_url"], P4, seen)
            b.knock(s5, ivy, room_a, p4)
            check(
                "allowed 5: a newly listed address signs up, reaches the room and asks to join",
                b.GUEST.fullmatch(p4) and landed == room_url(room_a) and b.members(ivy, room_a).get(p4) == "knock",
                f"{p4}; /register/continue: {s5.open_room}; membership {b.members(ivy, room_a).get(p4)}; steps:\n      {s5}",
            )
            s5b, result, html = refused(browser.new_context(bypass_csp=True), "a5-dropped", l1["invite_url"], P3, seen)
            check(
                "allowed 5: an address taken off the list is refused on the guest form, with no code sent",
                result["error"] == NOT_INVITED and result["code inputs"] == 0 and result["mail"] is None and not mails_to(P3),
                f"{result}; steps:\n      {s5b}",
            )
        except b.Abort as e:
            check("allowed 5 ran to the end", False, str(e))

        # 6. A participant is taken off the list after joining
        try:
            if p1 is None:
                raise b.Abort("no listed participant")
            r = put_link(ivy, l1["id"], room_a, [P2, P4])
            check(
                "allowed 6: the participant taken off the list stays joined",
                r.status_code == 200 and listed(l1["id"]) == [P2, P4] and b.members(ivy, room_a).get(p1) == "join",
                f"PUT {r.status_code}; MAS list now {listed(l1['id'])}; {p1} membership {b.members(ivy, room_a).get(p1)}",
            )
            s6, result, html = refused(browser.new_context(bypass_csp=True), "a6-removed", l1["invite_url"], P1, seen)
            check(
                "allowed 6: the next sign-up with their address is refused on the guest form, with no code sent",
                result["error"] == NOT_INVITED and result["code inputs"] == 0 and result["mail"] is None
                and len(mails_to(P1)) == 1,
                f"{result}; mails to {P1} in the whole run: {len(mails_to(P1))}; steps:\n      {s6}",
            )
        except b.Abort as e:
            check("allowed 6 ran to the end", False, str(e))
    finally:
        close(pw, browser)

    # The link API's refusals. The list must not change.
    before = listed(l1["id"])
    if p1:
        guest = b.personal_token(mas_user_id(p1), "p1guest")
        r = put_link(guest, l1["id"], room_a, [P1, P2, P4])
        check(
            "allowed API: PUT link/{id} from a guest who is a member of the room is 403, and the list stays",
            r.status_code == 403 and listed(l1["id"]) == before,
            f"{r.status_code} {r.text}; list {listed(l1['id'])}",
        )
    else:
        check("allowed API: PUT link/{id} from a guest", False, "no listed participant")
    r = put_link(nora, l1["id"], room_a, [P1, P2, P4])
    check(
        "allowed API: PUT link/{id} from a user who isn't in the room is 403, and the list stays",
        r.status_code == 403 and listed(l1["id"]) == before,
        f"{r.status_code} {r.text}; list {listed(l1['id'])}",
    )
    r = put_link(ivy, "01J00000000000000000000000", room_a, [P1])
    check("allowed API: PUT link/{id} for an unknown id is 404", r.status_code == 404, f"{r.status_code} {r.text}")
    r = put_link(ivy, l1["id"], room_b, [P1, P2, P4])
    check(
        "allowed API: PUT link/{id} naming another room the caller may invite to is 404, and the list stays",
        r.status_code == 404 and listed(l1["id"]) == before,
        f"{r.status_code} {r.text}; list {listed(l1['id'])}",
    )
    r = put_link(ivy, l1["id"], None, [P1, P2, P4])
    check(
        "allowed API: PUT link/{id} without a room_id is 400, and the list stays",
        r.status_code == 400 and listed(l1["id"]) == before,
        f"{r.status_code} {r.text}; list {listed(l1['id'])}",
    )
    url = mas_token(l1["id"])[1].get("continue_url")
    check(
        "allowed API: MAS holds the link's room as the client URL the module built, and no room_id",
        url == room_url(room_a) and "room_id" not in mas_token(l1["id"])[1],
        f"continue_url {url}",
    )
    return summary()


if __name__ == "__main__":
    sys.exit(main())
