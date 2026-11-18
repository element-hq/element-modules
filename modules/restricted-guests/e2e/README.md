# Guest invites end to end

Drives the guest invite flows through Element Web, MAS and Synapse with this
module, in headless Chromium, and checks MAS's admin API and the module's link
API along the way. A run takes about five minutes and prints one `PASS` or `FAIL`
line per check.

Screenshots of every step land in `screens/`, and logs and the mailbox in
`state/`.

## Checks

Each script's checks are below, by the name its `PASS` or `FAIL` line prints. A
journey that stops early fails one more check, "… ran to the end", with the
error.

### `gf_browser.py`: Element Web's "Invite guests" dialog (16)

An email invite. The inviter invites an address from the dialog, and the guest
follows the emailed link:

1. `inviter signs in to Element Web through MAS`
2. `Invite guests: the dialog offers to switch the room to Ask to join, and sends the invite`
3. `the invite email reaches the mail sink`
4. `invite email: subject, headline with the room and the inviter, approval line`
5. `email guest: MAS's register page shows the pinned address with no email, password or username field, and no providers`
6. `email guest: registered as a guest-<random> localpart, sent to the room in Element Web`
7. `email guest: consent skipped (MAS answered /consent with a redirect, not the page)`
8. `email guest: Ask to join, and Request to join knocks`
9. `inviter approves in Element Web, and the guest joins`

An open link. The inviter copies the dialog's link, and a second guest signs up
with a display name and no email:

10. `the dialog fetches an invite link once the room is Ask to join`
11. `link guest: MAS's register page asks for a display name, with no email, password or username field`
12. `link guest: registered as a guest-<random> localpart, sent to the room in Element Web`
13. `link guest: consent skipped`
14. `link guest: Ask to join, and Request to join knocks`

Consent is still shown for a guest's later sign-in, and for an older account:

15. `email guest's second sign-in (another Element Web, with a session already): consent shown`
16. `an account older than 120s signing in for the first time: consent shown`

### `gf_api.py`: MAS's admin API (28)

Minting a token pinned to an address and no room, and emailing it:

1. `API: mint a roomless token pinned to an address (201)`
2. `API: send a roomless pinned token (202, scheduled 1)`
3. `API: roomless email delivered to the pinned address`
4. `API: roomless email subject has no room`
5. `API: roomless email headline names the inviter and the server, no room`
6. `API: roomless email has no approval line`
7. `API: roomless email links to the token`

Emailing a token not pinned to an address:

8. `API: send an unpinned token to a given address (202)`
9. `API: unpinned token's email delivered to the given address`

What sending and minting refuse:

10. `API: an address that isn't the token's is refused (400)`
11. `API: an unknown token is 404`
12. `API: an unpinned token without an address is refused (400)`
13. `API: a mint pinning an address the policy refuses is 400`
14. `API: a template is stored as sent`: the `username` template `guest-{{ random }}`
15. `API: a mint with the old {random} syntax is 400`
16. `API: a mint with a template syntax error is 400`
17. `API: a mint with an unknown template variable is 400`
18. `API: a mint with an address that doesn't parse is 400`

The `continue_url` MAS sends a guest to after signing up:

19. `API: a mint keeps its continue_url as given (201)`
20. `API: /register/continue/{id} redirects to the continue_url, with no session`
21. `API: /register/continue/{id} for a token without a continue_url goes to /`
22. `API: a mint with a continue_url that is a matrix: URI is 400`
23. `API: a mint with a continue_url that is a javascript: URI is 400`
24. `API: a mint with a continue_url that is no scheme is 400`
25. `API: a mint with a continue_url that is a space is 400`
26. `API: a mint ignores room_id: MAS has no rooms`

Naming the room in the email:

27. `API: room_name is accepted for a token without a continue_url (202)`
28. `API: that email names the room and says someone will approve`

### `gf_allowed.py`: links that list the addresses allowed to sign up (20)

The inviter makes the links through the module's `invite_guests/link` API: one
listing three participants for room A, one listing one of them for room B, and
an open one for room B. The guests use Element Web.

1. `allowed API: POST link with emails is 200 with the token's id and invite_url, and MAS holds the list, deduplicated ignoring case`
2. `allowed API: POST link without emails is 200 with an id, and MAS holds no list`

Journey 1, a listed participant signs up:

3. `allowed 1: a listed link's register page asks for an email and sends a code, with no password, username or display name field, no providers, and no listed address`
4. `allowed 1: the listed participant registers as a guest-<random> localpart and /register/continue sends them to the room`
5. `allowed 1: the participant asks to join, is approved and joins`

Journey 2, an unlisted address is refused:

6. `allowed 2: an unlisted address gets the field error on the guest form, with no code sent, and the page names no listed address`

Journeys 3 and 4, the list holds sign-ups only, so a guest already signed in
goes straight to the room:

7. `allowed 3: a guest signed in with an address the link lists (in another case) goes straight to its room, with no sign-up`
8. `allowed 4: a guest signs up through an open link with a display name and no email`
9. `allowed 4: signed in, they open the listed link, go straight to its room with no sign-up, and ask to join`

Journey 5, the inviter replaces the list:

10. `allowed 5: PUT link/{id} by the inviter replaces the list: 200 with the same id and invite_url`
11. `allowed 5: a newly listed address signs up, reaches the room and asks to join`
12. `allowed 5: an address taken off the list is refused on the guest form, with no code sent`

Journey 6, a participant who already joined is taken off the list:

13. `allowed 6: the participant taken off the list stays joined`
14. `allowed 6: the next sign-up with their address is refused on the guest form, with no code sent`

What the link API refuses, and what MAS holds:

15. `allowed API: PUT link/{id} from a guest who is a member of the room is 403, and the list stays`
16. `allowed API: PUT link/{id} from a user who isn't in the room is 403, and the list stays`
17. `allowed API: PUT link/{id} for an unknown id is 404`
18. `allowed API: PUT link/{id} naming another room the caller may invite to is 404, and the list stays`
19. `allowed API: PUT link/{id} without a room_id is 400, and the list stays`
20. `allowed API: MAS holds the link's room as the client URL the module built, and no room_id`

### `gf_back.py`: going Back after signing up (1)

Chromium, with the back-forward cache on, restores MAS's filled register form
after a guest signs up through an open link:

1. `link guest going Back: the restored form, submitted again, registers no second guest`

## What runs

| Part                       | Source                                                                                         |
| -------------------------- | ---------------------------------------------------------------------------------------------- |
| The Synapse module         | This checkout's `../synapse`                                                                   |
| MAS                        | `quenting/guest-invite-link-design` merged with `devonh/skip-consent`, fetched by `sources.sh` |
| Element Web and its module | `aea209b6bf` (from `florianduros/email-invitation`), fetched by `sources.sh`                   |
| Synapse                    | 1.165.0                                                                                        |
| Mail                       | aiosmtpd on :1025, writing `state/maildir`                                                     |

Everything is on localhost: Synapse on :8008, MAS on :8080 with its admin API on
:8082, and Element Web on :8090 (and :8091 for one check). The configs are in
`config/`.

## Running it with Docker

Needs Docker with Compose v2.17 or later.

```sh
./sources.sh    # MAS and Element Web into src/
./compose.sh    # build, start, run every check, stop
```

The first run builds MAS (a release build) and Element Web, which takes a while.
`compose.sh` exits non-zero if a check fails, and leaves every container's
logs in `state/compose.log`.

## Running it locally

Needs Rust, Node.js 22.18 or later, pnpm, `opa` (for MAS's policies),
PostgreSQL with `psql`, Python 3.10 or later and `curl`.

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt 'matrix-synapse[postgres]==1.165.0'
.venv/bin/playwright install chromium
./sources.sh
./build.sh                          # mas-cli and its assets, and Element Web, into work/
GF_PYTHON=.venv/bin/python ./stack.sh run
```

`stack.sh start` and `stack.sh stop` start and stop the stack without running
the checks, to look at it by hand.

## Settings

| Variable                                   | Default                                                 | For                                                        |
| ------------------------------------------ | ------------------------------------------------------- | ---------------------------------------------------------- |
| `GF_MAS_BRANCHES`                          | `quenting/guest-invite-link-design devonh/skip-consent` | `sources.sh`: the MAS branches to merge                    |
| `GF_ELEMENT_WEB_REF`                       | `aea209b6bf639ff830fa2aab0d870b47fc78f55e`              | `sources.sh`: the Element Web commit, branch or tag        |
| `GF_MAS_SRC`, `GF_ELEMENT_WEB_SRC`         | `src/mas`, `src/element-web`                            | Build from other checkouts                                 |
| `GF_MODULE_SRC`                            | `../synapse`                                            | Run another copy of the module                             |
| `GF_SYNAPSE_VERSION`                       | `1.165.0`                                               | `compose.sh`: the Synapse image                            |
| `GF_WORK`                                  | `work`                                                  | `build.sh`, `stack.sh`: where the builds go                |
| `GF_PYTHON`                                | `python3`                                               | `stack.sh`: the Python with `requirements.txt` and Synapse |
| `PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD` | `localhost`, `5432`, `postgres`, `postgres`             | `stack.sh`: the PostgreSQL server                          |
| `GF_CHROMIUM`                              | Playwright's Chromium                                   | Another Chromium                                           |

## Things to know

- `stack.sh run` and `compose.sh` restart MAS twice, because MAS keeps its rate
  limits in memory.
- `gf_browser.py` waits for an account to be older than the 120 seconds
  `skip_consent.max_account_age_seconds` allows, so it sits idle for a while.
- Element Web is a development build, because the production build was
  OOM-killed with 7 GB of memory.
