# Copyright 2026 Element Creations Ltd.
#
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Element-Commercial
# Please see LICENSE files in the project root for full details.

import json
import logging
import secrets
import string
from typing import Any, Callable, Dict, List, Optional, Tuple

from synapse.api.errors import HttpResponseException
from synapse.api.ratelimiting import Ratelimiter
from synapse.config.ratelimiting import RatelimitSettings
from synapse.event_auth import get_named_level, get_user_power_level
from synapse.http.site import SynapseRequest
from synapse.module_api import (
    DirectServeJsonResource,
    EventBase,
    ModuleApi,
    StateMap,
    parse_json_object_from_request,
)

from synapse_guest_module.config import GuestModuleConfig
from synapse_guest_module.mas_admin_client import MasAdminClient

logger = logging.getLogger("synapse.contrib." + __name__)


class GuestInviteServlet(DirectServeJsonResource):
    """The `POST /_synapse/client/invite_guests` endpoint invites a list of email
    addresses to a room as guests. It requires the `room_id` and `emails`
    properties.

    Each address is emailed a link to register as one specific guest, which MAS
    mints an invite code for and sends out. Nothing exists on this homeserver
    until a recipient follows their link: the localparts are only reserved by
    the invite codes they are pinned to.
    """

    def __init__(
        self,
        config: GuestModuleConfig,
        api: ModuleApi,
        mas_admin_client: MasAdminClient,
        is_module_guest: Callable[[str], bool],
    ):
        super().__init__()
        self._api = api
        self._config = config
        self._mas_admin_client = mas_admin_client
        self._is_module_guest = is_module_guest

        # Per worker, and reset on restart
        per_hour = config.email_invites.per_inviter_per_hour
        self._ratelimiter = Ratelimiter(
            store=api._hs.get_datastores().main,
            clock=api._hs.get_clock(),
            cfg=RatelimitSettings(
                key="guest_module_invite_guests",
                per_second=per_hour / 3600,
                burst_count=per_hour,
            ),
        )

    async def _async_render_POST(
        self, request: SynapseRequest
    ) -> Tuple[int, Dict[str, Any]]:
        """Generate a guest localpart per address, have MAS
        mint an invite code for each and email out the links.
        Email sending is handled by MAS.
        """

        requester = await self._api.get_user_by_req(request)

        json_dict = parse_json_object_from_request(request)

        room_id = json_dict.get("room_id")
        if not isinstance(room_id, str) or not room_id.startswith("!"):
            return 400, {"msg": "You must provide a valid 'room_id'"}

        emails = json_dict.get("emails")
        if (
            not isinstance(emails, list)
            or len(emails) == 0
            or not all(
                isinstance(email, str) and len(email.strip()) > 0 for email in emails
            )
        ):
            return 400, {
                "msg": "You must provide 'emails' as a non-empty list of strings"
            }

        # Keyed ignoring case, keeping the first spelling of each address
        unique_emails: Dict[str, str] = {}
        for email in emails:
            unique_emails.setdefault(email.strip().lower(), email.strip())

        max_emails = self._config.email_invites.max_emails
        if len(unique_emails) > max_emails:
            return 400, {"msg": f"You can invite at most {max_emails} emails at once"}

        user_id = requester.user.to_string()
        if self._is_module_guest(user_id):
            return 403, {"msg": "Guests can't invite guests"}

        state = await self._api.get_room_state(
            room_id,
            [
                ("m.room.create", ""),
                ("m.room.join_rules", ""),
                ("m.room.member", user_id),
                ("m.room.name", ""),
                ("m.room.power_levels", ""),
            ],
        )
        if not self._may_invite(user_id, state):
            return 403, {"msg": "You are not allowed to invite users to this room"}

        # An email-invited guest has no Matrix invite, so it gets in by asking to
        # join, and Element Web offers that only for `knock`, not `knock_restricted`
        join_rules = state.get(("m.room.join_rules", ""))
        if join_rules is None or join_rules.content.get("join_rule") != "knock":
            return 403, {
                "msg": "Guests can only be invited to rooms they can ask to join",
                "reason": "room_not_knockable",
            }

        if room_id in self._config.rooms_forbidden_to_guests:
            return 403, {"msg": "Guests are forbidden from this room"}

        # Last, so that a refused request doesn't spend the limit
        await self._ratelimiter.ratelimit(requester, n_actions=len(unique_emails))

        invites: List[Dict[str, str]] = []
        for email in unique_emails.values():
            localpart = self._config.user_id_prefix + "".join(
                secrets.choice(string.ascii_lowercase + string.digits)
                for _ in range(32)
            )
            invites.append({"email": email, "username": localpart})

        logger.info(
            "'%s' is inviting %d guest(s) to '%s'", user_id, len(invites), room_id
        )
        room_name = _non_empty_string(state.get(("m.room.name", "")), "name")
        inviter_name = _non_empty_string(
            state.get(("m.room.member", user_id)), "displayname"
        )
        try:
            # Outside the inner `try`, because a refused token request is between
            # this module and MAS, not the inviter's to see
            token = await self._mas_admin_client.request_admin_token()
            try:
                scheduled = await self._mas_admin_client.invite_guests(
                    room_id, room_name, user_id, inviter_name, invites, token
                )
            except HttpResponseException as e:
                if e.code == 400:
                    return 400, {
                        "msg": _first_error_title(e.response)
                        or "MAS refused the invites"
                    }
                if e.code == 404:
                    logger.warning(
                        "MAS answered guest invites with 404: it's too old, has them "
                        "turned off, or isn't at 'mas.admin_api_base_url'"
                    )
                    return 404, {"msg": "Inviting guests by email is turned off"}
                raise
        # A timeout is a `SynapseError`, and a connection failure a Twisted error
        except Exception:
            logger.exception("Failed to send guest invites to MAS")
            return 502, {"msg": "Failed to send the invites"}

        return 202, {"scheduled": scheduled}

    @staticmethod
    def _may_invite(user_id: str, state: StateMap[EventBase]) -> bool:
        """Whether this user may invite guests to the room with this state.

        The guests are invited by email rather than by a membership event, so
        nothing else checks this. It mirrors what Synapse requires of a real
        invite: the user is joined to the room and meets its invite power level.
        """
        # A room this server isn't in has no state, not even the create event
        # that `get_user_power_level` asserts
        member = state.get(("m.room.member", user_id))
        if member is None or member.content.get("membership") != "join":
            return False

        return get_user_power_level(user_id, state) >= get_named_level(
            state, "invite", 0
        )


def _non_empty_string(event: Optional[EventBase], key: str) -> Optional[str]:
    """The event's content value for this key, if it's a non-empty string.

    Room members set these, so they can hold anything.
    """
    value = event.content.get(key) if event is not None else None
    return value if isinstance(value, str) and value else None


def _first_error_title(body: bytes) -> Optional[str]:
    """The first title in a MAS admin API error body, `{"errors": [{"title"}]}`."""
    try:
        title = json.loads(body)["errors"][0]["title"]
    except (ValueError, LookupError, TypeError):
        return None
    return title if isinstance(title, str) else None
