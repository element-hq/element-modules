"""Going Back after registering through an open invite link: Chromium, with the
back-forward cache on as in a real browser, restores MAS's filled register form;
submitting it again goes back to the room and registers no second guest."""

import json
import os
import re
import sys
import time

from browser import _PROXY_VARS, CHROMIUM
from playwright.sync_api import sync_playwright

import gf_allowed as a
import gf_browser as g
from gf_common import admin, admin_token, check, summary

label = "back"


def guests():
    r = admin("GET", "/users?page[first]=100", admin_token())
    return sorted(
        u["attributes"]["username"] for u in r.json()["data"] if u["attributes"]["username"].startswith("guest-")
    )


ina = g.personal_token(g.new_user(f"ina{label}", g.PASSWORD), f"ina{label}")
room_id = a.knock_room(ina, "Back room")
r = a.make_link(ina, room_id)
link = r.json()["invite_url"]

pw = sync_playwright().start()
browser = pw.chromium.launch(
    executable_path=CHROMIUM,
    headless=True,
    args=["--no-sandbox", "--no-proxy-server"],
    ignore_default_args=["--disable-back-forward-cache"],
    env={k: v for k, v in os.environ.items() if k not in _PROXY_VARS},
)
ctx = browser.new_context(bypass_csp=True)
ctx.add_init_script("window.addEventListener('pageshow', e => { window.__restored = e.persisted; });")
page = ctx.new_page()
s = g.Steps(page, f"back-{label}")
posts = []
page.on("request", lambda q: q.method == "POST" and q.url.startswith(f"{g.MAS}/register") and posts.append(q.url))
out = {"link": link}
try:
    before = guests()
    page.goto(link)
    page.locator("input[name=display_name]").fill("Back probe")
    s.shot("form")
    page.get_by_role("button", name="Continue").click()
    page.wait_for_url(re.compile(rf"^{re.escape(g.ELEMENT)}/"), timeout=g.TIMEOUT)
    time.sleep(3)
    out["landed"] = page.url
    out["guests after registering"] = sorted(set(guests()) - set(before))

    out["back trail"] = []
    for _ in range(5):
        if page.url.startswith(f"{g.MAS}/register?"):
            break
        # A page restored from the back-forward cache fires no load event
        page.go_back(wait_until="commit")
        time.sleep(1.5)
        out["back trail"].append(page.url)
    s.shot("after-back")
    out["restored from back-forward cache"] = page.evaluate("window.__restored")
    name = page.locator("input[name=display_name]:visible")
    out["form shown"] = page.url.startswith(f"{g.MAS}/register?") and name.count() == 1
    if out["form shown"]:
        out["display name kept"] = name.input_value()
        if not out["display name kept"]:
            name.fill("Back probe")
        page.get_by_role("button", name="Continue").click()
        page.wait_for_url(re.compile(rf"^{re.escape(g.ELEMENT)}/"), timeout=g.TIMEOUT)
        time.sleep(3)
        s.shot("after-resubmit")
    out["url at the end"] = page.url
    out["register POSTs"] = posts
    out["guests at the end"] = sorted(set(guests()) - set(before))
    check(
        "link guest going Back: the restored form, submitted again, registers no second guest",
        out["restored from back-forward cache"] and out["form shown"] and len(out["register POSTs"]) == 2
        and len(out["guests at the end"]) == 1 and out["url at the end"].startswith(g.ELEMENT),
        json.dumps(out),
    )
except Exception as e:
    check("link guest going Back ran to the end", False, f"{e!r} {json.dumps(out)}")
finally:
    browser.close()
    pw.stop()
sys.exit(summary())
