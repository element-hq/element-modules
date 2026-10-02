# Copyright 2026 Element Creations Ltd.
#
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Element-Commercial
# Please see LICENSE files in the project root for full details.

import logging
import secrets
import string
from typing import Any, Dict, List, Tuple

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
    ):
        super().__init__()
        self._api = api
        self._config = config
        self._mas_admin_client = mas_admin_client

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

        user_id = requester.user.to_string()
        state = await self._api.get_room_state(
            room_id,
            [
                ("m.room.create", ""),
                ("m.room.member", user_id),
                ("m.room.power_levels", ""),
            ],
        )
        if not self._may_invite(user_id, state):
            return 403, {"msg": "You are not allowed to invite users to this room"}

        invites: List[Dict[str, str]] = []
        for email in emails:
            localpart = self._config.user_id_prefix + "".join(
                secrets.choice(string.ascii_lowercase + string.digits)
                for _ in range(32)
            )
            invites.append({"email": email.strip(), "username": localpart})

        logger.info(
            "'%s' is inviting %d guest(s) to '%s'", user_id, len(invites), room_id
        )
        scheduled = await self._mas_admin_client.send_room_invites(room_id, invites)

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
