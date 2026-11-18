"""Helpers shared by the guest flows checks: MAS admin calls and the mail sink."""

import email
import email.policy
import mailbox
import os
import re
import time

import requests

MAS = "http://localhost:8080"
ADMIN = "http://localhost:8082/api/admin/v1"
CLIENT = ("01M42400CB0MQ37T1MHZ6W5MGP", "81eaf2b254bcf74e0cdb968599373fd471173d152b6dddb9")
MAILDIR = os.environ.get("GF_MAILDIR", f"{os.path.dirname(os.path.abspath(__file__))}/state/maildir")

session = requests.Session()
session.trust_env = False

results = []


def check(name, ok, evidence=""):
    results.append((name, bool(ok), evidence))
    print(f"{'PASS' if ok else 'FAIL'}: {name}" + (f" -- {evidence}" if evidence else ""), flush=True)
    return ok


def admin_token():
    r = session.post(
        f"{MAS}/oauth2/token",
        auth=CLIENT,
        data={"grant_type": "client_credentials", "scope": "urn:mas:admin"},
    )
    r.raise_for_status()
    return r.json()["access_token"]


def admin(method, path, token, **kwargs):
    return session.request(
        method, f"{ADMIN}{path}", headers={"Authorization": f"Bearer {token}"}, **kwargs
    )


def mails():
    """Every message in the sink, oldest first, as (to, subject, plain text, html)"""
    out = []
    try:
        box = mailbox.Maildir(MAILDIR, factory=None, create=False)
    except FileNotFoundError:
        return out
    for key in sorted(box.keys()):
        msg = email.message_from_bytes(box.get_bytes(key), policy=email.policy.default)
        plain = msg.get_body(("plain",))
        html = msg.get_body(("html",))
        out.append(
            {
                "key": key,
                "to": str(msg["To"]),
                "subject": str(msg["Subject"]),
                "date": msg["Date"],
                "text": plain.get_content() if plain else "",
                "html": html.get_content() if html else "",
            }
        )
    return out


def wait_mail(to, seen=(), timeout=30, subject_re=None):
    """The first message to `to` whose key isn't in `seen`"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        for m in mails():
            if m["key"] in seen or to.lower() not in m["to"].lower():
                continue
            if subject_re and not re.search(subject_re, m["subject"]):
                continue
            return m
        time.sleep(0.5)
    return None


def link_in(text):
    m = re.search(r"http://localhost:8080/register\?token=[A-Za-z0-9%+_.-]+", text)
    return m.group(0) if m else None


def code_in(text):
    m = re.search(r"\b(\d{6})\b", text)
    return m.group(1) if m else None


def summary():
    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} passed", flush=True)
    return 1 if failed else 0
