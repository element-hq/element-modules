# Synapse Guest Module

A [pluggable synapse module](https://element-hq.github.io/synapse/latest/modules/index.html) to restrict the actions of guests.

**Features:**

1. Provides an endpoint that creates temporary users with a same pattern (default: `guest-[randomstring]`).
2. The temporary users have a mandatory displayname suffix (default: ` (Guest)`) that they can't remove from their profile.
3. The temporary users are limited in what they can do (examples: create room, invite users).
4. The temporary users won't be returned by the user directory search results, and the temporary users themselves get an empty user directory: they should not be handed a browsable index of users they have no relationship with.
5. The temporary users are disabled after an expiration timeout (default: `24 hours`).
6. Provides an endpoint that invites people by email to ask to join a room, which MAS emails a personal invite link for (opt-in).

## Compatibility

This module requires Synapse 1.122.0 or later: the first release that tells the user directory spam checker who is searching, which the module needs to give guests an empty directory. On anything older, user directory searches fail with an internal error once the module is loaded.

Gating the room directory (`hide_room_directory_from_guests`) is opt-in and disabled by default because it monkey-patches Synapse's internal `RoomListHandler`; Synapse has no module callback there. The patch was verified against Synapse 1.159, and the test suite re-verifies the patched internals against the installed Synapse. The module refuses to start if the methods it replaces have been renamed or re-shaped, but it cannot tell when a future Synapse stops recording the caller's user ID on the request's logging context: guests would then silently see the full room directory again. Do not rely on this option as the only control. Guests receive the same empty response Synapse serves when `enable_room_list_search` is disabled.

## Synapse configuration

This modules requires that the homeserver has the following configuration in their `homeserver.yaml`:

```yaml
# Required so Element is able to show the room preview where the user can login.
# Only applies to legacy deployments that have not delegated authentication to
# matrix-authentication-service: under MAS this option is inert, and the guest login
# flow it enables does not exist.
allow_guest_access: true
```

If `hide_room_directory_from_guests` is enabled, `allow_public_rooms_without_auth` must be left at its default of `false`. With it enabled the room directory is readable without an access token and therefore cannot be gated per-user, and the module refuses to start.

## Module installation

Copy the `synapse_guest_module` folder into the python modules path.
This can also be achieved by the [`PYTHONPATH` environment variable](https://docs.python.org/3/using/cmdline.html#envvar-PYTHONPATH).

Add module configuration into `modules` section of `homeserver.yaml`:

```yaml
modules:
    - module: synapse_guest_module.GuestModule
      config: {}
```

## Module configuration

The module provides (optional) configuration options:

- `user_id_prefix` - the prefix of the usernames that are created by this module. Default: `guest-`.
- `display_name_suffix` - the suffix added to the display name of guest users. Default: ` (Guest)`.
- `enable_user_reaper` - if true, the module disables all users that are older than the configured expiration time. Default: `true`.
- `user_expiration_seconds` - the expiration time in seconds when a guest user expires after their creation. Default: `86400` (=24 hours).
- `hide_room_directory_from_guests` - if true, guests get an empty public room directory, including the `?server=` proxy to remote directories. Default: `false`.

    This option monkey-patches Synapse internals (see [Compatibility](#compatibility)) and can silently stop working on a future Synapse. Deployments that leave it off can set `enable_room_list_search: false` in `homeserver.yaml` instead, which hides the directory from every user.

- `rooms_forbidden_to_guests` - room IDs (not aliases — the module refuses aliases at startup) that guests must never be a member of, for example a hidden room that every user is auto-joined to. Guests are refused a join to these rooms even when they have been invited, and invites of guests into them are rejected. Default: `[]`.

    This matters because membership of a room exposes its full member list over `/rooms/{roomId}/members`: a guest in a server-wide room can enumerate every user on the server, which is what hiding the user directory from guests is there to prevent. The join refusal is what enforces it — server admins bypass the invite check.

    Denying an auto-join makes Synapse log an ERROR with a full traceback for each guest registration ("Failed to join new user to ..." naming the alias from `auto_join_rooms`). That is harmless: Synapse catches the failure per room, and registration still succeeds. When adopting `rooms_forbidden_to_guests` on an existing deployment, kick the guests that have already joined those rooms once; the option only prevents new joins.

If matrix-authentication-service (MAS) is configured, the module will need to
interface with it in order to register/deactivate users. Provide the below
options in order to give the module access to [MAS' Admin
API](https://element-hq.github.io/matrix-authentication-service/topics/admin-api.html).

- `mas` - optional configuration for Matrix Authentication Service (MAS). When set, the module creates users via MAS' admin API.
    - `admin_api_base_url` - Base URL for MAS' admin API (e.g. `https://mas.example.org`). Trailing slashes will be automatically stripped.
    - `oauth_base_url` - Base URL for MAS' OAuth endpoints (defaults to `admin_api_base_url` if not set). Trailing slashes will be automatically stripped.
    - `client_id` - client ID for the automated tool. Must be a valid [ULID](https://github.com/ulid/spec). Generate one [here](https://ulidtools.com/).
    - `client_secret` - client secret for the automated tool. Ideally long and cryptographically secure. Keep it a secret!
    - `client_secret_filepath` - path to a plaintext file containing the client secret. If set, this is used instead of `client_secret`.

- `email_invites` - optional configuration for [inviting guests by email](#inviting-guests-by-email). Requires `mas`.
    - `enabled` - if true, the module serves `/_synapse/client/invite_guests`. Only enable it on a server with closed registration (see the [deployment checklist](#deployment-checklist)). Default: `false`.
    - `max_emails` - the most addresses one request can invite. It can't exceed `per_inviter_per_hour`. Default: `20`.
    - `per_inviter_per_hour` - how many addresses one user can invite per hour, on average. Up to this many can go at once, and the allowance then refills over the next hour, so one hour can see nearly twice this many. Each worker counts separately, and the count resets when Synapse restarts. Default: `50`.

Example configuration:

```yaml
modules:
    - module: synapse_guest_module.GuestModule
      config:
          # Use a german suffix
          display_name_suffix: " (Gast)"
          # Hide the public room directory from guests (opt-in, see Compatibility)
          hide_room_directory_from_guests: true
          # Guests may never join these rooms, invited or not
          rooms_forbidden_to_guests:
              - "!allUsers:example.org"
          # The below is required if using MAS
          mas:
              admin_api_base_url: https://mas.example.org
              oauth_base_url: https://mas.example.org
              # The `client_id` must be a valid ULID:
              # https://github.com/ulid/spec
              # Generate ULID's easily at:
              # https://ulidtools.com/
              client_id: 000000000000000000000G0EST
              client_secret: your-client-secret
              # Alternatively, load the secret from a file:
              # client_secret_filepath: /run/secrets/mas-client-secret
          # Invite guests by email (requires `mas`)
          email_invites:
              enabled: true
              max_emails: 20
              per_inviter_per_hour: 50
```

Enable [the Admin API on a MAS
listener](https://element-hq.github.io/matrix-authentication-service/topics/admin-api.html#enabling-the-api).
Then, add the following to your MAS config file:

```yaml
policy:
    data:
        admin_clients:
            - 000000000000000000000G0EST

# ...

clients:
    # The `client_id` must be a valid ULID https://github.com/ulid/spec
    # Generate ULID's easily at: https://ulidtools.com/
    - client_id: 000000000000000000000G0EST
      # The guest module uses the client_secret_basic authentication method.
      client_auth_method: client_secret_basic
      client_secret: your-client-secret
```

## Inviting guests by email

`POST /_synapse/client/invite_guests` invites a list of email addresses to ask to
join a room as guests. It's served when `email_invites.enabled` is set, and needs the
`mas` configuration above: MAS mints the invite codes, sends the emails and registers
the guests. MAS has to support guest invites and have them turned on: otherwise this
endpoint answers 404.

```json
{
    "room_id": "!room:example.org",
    "emails": ["alice@example.com", "bob@example.com"]
}
```

The caller must be joined to the room and meet its `invite` power level, the same
as for inviting a user directly, and can't be a guest. The room's join rule must be
`knock` (Ask to join), and the room can't be in `rooms_forbidden_to_guests`.
Addresses are deduplicated ignoring case, and each counts once against `max_emails`
and `per_inviter_per_hour`.

Each address gets an invite code of its own, pinned to that address and to a fresh
guest localpart, which MAS emails a link for, naming the room and the caller. The
links only ever reach the recipients, so they are not in the response:

```json
{ "scheduled": 2 }
```

A recipient who follows their link signs up as the guest the code names, or signs
in with an existing account, and lands on the room. There they ask to join, and a
member who can invite approves them. Nothing exists on this homeserver until they
sign up, and this endpoint doesn't send a room invite.

| Status | When                                                                                                                                                                                                                                                                                      |
| ------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 400    | `room_id` or `emails` is missing or malformed, there are more than `max_emails` addresses, or MAS refuses the request, with its message in `msg`                                                                                                                                          |
| 403    | The caller is a guest, isn't joined to the room or is below its `invite` level, or the room is forbidden to guests or its join rule isn't `knock`. For the join rule, the body also has `"reason": "room_not_knockable"`. Synapse's own invite controls can refuse a request too (below). |
| 404    | MAS has guest invites turned off                                                                                                                                                                                                                                                          |
| 429    | The caller is over `per_inviter_per_hour`. The body is Synapse's usual rate-limit error, with `retry_after_ms`. Users Synapse exempts from rate limits, through the admin API's rate-limit override or an application service with `rate_limited: false`, aren't limited.                 |
| 502    | MAS failed or couldn't be reached                                                                                                                                                                                                                                                         |

Three of Synapse's own controls on email invites apply here too, and refuse with a 403:

- `block_non_admin_invites` refuses callers who aren't server admins, as Synapse
  decides it. Under MAS, that means the access token has the `urn:synapse:admin:*`
  scope, so an admin signed in to Element Web with an ordinary token is refused too,
  as with Synapse's own invites.
- A third-party rules module's `check_threepid_can_be_invited` and a spam checker's
  `user_may_send_3pid_invite` run for each address. If either refuses one, the whole
  request is refused.

Synapse's `rc_third_party_invite` rate limit doesn't apply: `per_inviter_per_hour` is
the limit instead.

The user reaper doesn't deactivate guests who signed up from an invite email: it
only knows about the guests `register_guest` creates. List them with MAS' admin API,
`GET /api/admin/v1/users?filter[search]=guest-`, and deactivate them there.

Sending the emails needs MAS' task worker running. `mas-cli server` runs it unless
started with `--no-worker`, and [`mas-cli worker`](https://element-hq.github.io/matrix-authentication-service/reference/cli/worker.html)
runs it on its own. MAS also needs an [email
sender](https://element-hq.github.io/matrix-authentication-service/reference/configuration.html#email).

### Deployment checklist

1. Give the module access to MAS, as in [Module configuration](#module-configuration): the module's client in MAS' `policy.data.admin_clients`, and the module's `mas` block.
2. In MAS, set `guest_invites.enabled` and `guest_invites.client_room_url`, so that a link lands on its room in your client.
3. Set `email_invites.enabled` only on a server with closed registration. Anyone who can register can create a knock room, and then have your server email `max_emails` addresses per request about it, with a room name and display name they chose. `per_inviter_per_hour` doesn't stop someone with many accounts.

    Set `enable_guest_registration: false` only once the Element Web module's `guest_registration` flag has shipped and is off: until then, its login footer still calls `register_guest`.

4. In Element Web's `config.json`, set `"features": {"feature_ask_to_join": true}`. Without it, rooms can't be set to Ask to join, invitees aren't offered to ask, and members aren't shown the requests.
5. Use the same guest prefix in the module's `user_id_prefix` and the Element Web module's `guest_user_prefix` (with `@`).
6. **Invite colleagues by Matrix ID, not by email.** Tell colleagues who get an invite email to choose Sign in, not the guest form. A guest account created with a colleague's address blocks that colleague's first sign-in with SSO, at "email in use".
7. Check MAS' policy data. Guests sign up through MAS' password registration, even without a password, so its registration policy applies to them. `policy.data.allowed_domains`, `banned_domains` and `emails` can refuse the invited address: a list that keeps self-registration to staff refuses every guest. `registration.allowed_usernames` and `banned_usernames` can refuse the guest's username: banning the guest prefix refuses every invite. MAS also checks the policy when it mints the invites, so the endpoint answers 400 naming the refusal. Policy data changed after an invite was sent still refuses the invitee on the guest form.
8. Set up SPF, DKIM and DMARC for the domain MAS sends email from.
9. Don't turn on MAS' `experimental.inactive_session_expiration.expire_user_sessions`. A guest's only way back in is their MAS browser session.
10. Set `hide_room_directory_from_guests: true`, and list the rooms guests mustn't reach in `rooms_forbidden_to_guests`. A guest can ask to join any knock room they can name, local or remote, not only the rooms they were invited to.

## Production installation

The module is not published to a python registry, but we provide a docker container that can be used as an `initContainer` in Kubernetes:

```diff
  apiVersion: apps/v1
  kind: "StatefulSet"
  metadata:
    name: synapse
  spec:
    # ...
    template:
      spec:
+       # The init container copies the module to the `synapse-modules` volume
+       initContainers:
+         - image: ghcr.io/element-hq/synapse-guest-module:<version>
+           name: install-guest-module
+           volumeMounts:
+           - mountPath: /modules
+             name: synapse-modules
        containers:
          - name: "synapse"
            image: "matrixdotorg/synapse:v1.87.0"
+           env:
+             # Tell python to read the modules from the `/modules` directory
+             - name: PYTHONPATH
+               value: /modules
+           volumeMounts:
+             # Mount the `synapse-modules` volume
+             - mountPath: /modules
+               name: synapse-modules
            # ...
+       # Use a local volume to store the module
+       volumes:
+         - emptyDir:
+             medium: Memory
+             sizeLimit: 50Mi
+           name: synapse-modules
          # ...
```

## Copyright & License

Copyright 2023 Nordeck IT + Consulting GmbH  
Copyright (c) 2025 New Vector Ltd

This software is multi licensed by New Vector Ltd (Element). It can be used either:

(1) for free under the terms of the GNU Affero General Public License (as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version); OR

(2) under the terms of a paid-for Element Commercial License agreement between you and Element (the terms of which may vary depending on what you and Element have agreed to).

Unless required by applicable law or agreed to in writing, software distributed under the Licenses is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the Licenses for the specific language governing permissions and limitations under the Licenses.
