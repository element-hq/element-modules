# Copyright 2026 Element Creations Ltd.
#
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Element-Commercial
# Please see LICENSE files in the project root for full details.

import json
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional, Tuple

from synapse.api.constants import EventContentFields, EventTypes, JoinRules, Membership
from synapse.api.errors import HttpResponseException
from synapse.api.ratelimiting import Ratelimiter
from synapse.config.ratelimiting import RatelimitSettings
from synapse.event_auth import get_named_level, get_user_power_level
from synapse.http.site import SynapseRequest
from synapse.module_api import (
    NOT_SPAM,
    DirectServeJsonResource,
    EventBase,
    ModuleApi,
    Requester,
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

    Each address is emailed a link to register as a guest, which MAS mints an
    invite code for and sends out. Nothing exists on this homeserver until a
    recipient follows their link, and MAS assigns the guest's localpart then.
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
        self._auth = api._hs.get_auth()
        self._server_config = api._hs.config.server
        callbacks = api._hs.get_module_api_callbacks()
        self._spam_checker = callbacks.spam_checker
        self._third_party_rules = callbacks.third_party_event_rules

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
        """Have MAS mint an invite code per address and email out the links.
        MAS assigns each guest's localpart from the username template.
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
        state, refusal = await self._check_room(requester, room_id)
        if refusal is not None:
            return refusal

        # The checks on each address are Synapse's own, as it makes them for
        # email invites
        for email in unique_emails.values():
            if not await self._third_party_rules.check_threepid_can_be_invited(
                medium="email", address=email, room_id=room_id
            ) or (
                await self._spam_checker.user_may_send_3pid_invite(
                    inviter_userid=user_id,
                    medium="email",
                    address=email,
                    room_id=room_id,
                )
                != NOT_SPAM
            ):
                return 403, {"msg": f"You can't invite {email} to this room"}

        # Last, so that a refused request doesn't spend the limit
        await self._ratelimiter.ratelimit(requester, n_actions=len(unique_emails))

        # MAS fills in `{random}` when the guest registers
        username = f"{self._config.user_id_prefix}{{random}}"
        expires_at = datetime.fromtimestamp(
            self._api._hs.get_clock().time()
            + self._config.email_invites.invite_lifetime,
            tz=timezone.utc,
        )

        logger.info(
            "'%s' is inviting %d guest(s) to '%s'", user_id, len(unique_emails), room_id
        )
        room_name = _non_empty_string(
            state.get((EventTypes.Name, "")), EventContentFields.ROOM_NAME
        )
        inviter_name = _non_empty_string(
            state.get((EventTypes.Member, user_id)),
            EventContentFields.MEMBERSHIP_DISPLAYNAME,
        )
        try:
            # Outside the inner `try`, because a refused token request is between
            # this module and MAS, not the inviter's to see
            token = await self._mas_admin_client.request_admin_token()
            try:
                # Every address is minted for before any is sent, so a refused
                # address sends no email at all
                registration_tokens = [
                    await self._mas_admin_client.create_registration_token(
                        username,
                        room_id,
                        token,
                        email=email,
                        usage_limit=1,
                        expires_at=expires_at,
                    )
                    for email in unique_emails.values()
                ]
                scheduled = await self._mas_admin_client.send_invite_emails(
                    [
                        registration_token.id
                        for registration_token in registration_tokens
                    ],
                    room_name,
                    user_id,
                    inviter_name,
                    token,
                )
            except HttpResponseException as e:
                if e.code == 400:
                    return 400, {
                        "msg": _first_error_title(e.response)
                        or "MAS refused the invites"
                    }
                if e.code == 404:
                    logger.warning(
                        "MAS answered guest invites with 404: it's too old or isn't "
                        "at 'mas.admin_api_base_url'"
                    )
                raise
        # A timeout is a `SynapseError`, and a connection failure a Twisted error
        except Exception:
            logger.exception("Failed to send guest invites to MAS")
            return 502, {"msg": "Failed to send the invites"}

        return 202, {"scheduled": scheduled}

    async def _check_room(
        self, requester: Requester, room_id: str
    ) -> Tuple[StateMap[EventBase], Optional[Tuple[int, Dict[str, Any]]]]:
        """The room's state, and the response refusing the request if the
        requester may not invite guests to the room.
        """
        user_id = requester.user.to_string()
        if self._is_module_guest(user_id):
            return {}, (403, {"msg": "Guests can't invite guests"})

        # Synapse's own control, as it applies it to email invites
        if (
            self._server_config.block_non_admin_invites
            and not await self._auth.is_server_admin(requester)
        ):
            return {}, (403, {"msg": "Invites have been disabled on this server"})

        state = await self._api.get_room_state(
            room_id,
            [
                (EventTypes.Create, ""),
                (EventTypes.JoinRules, ""),
                (EventTypes.Member, user_id),
                (EventTypes.Name, ""),
                (EventTypes.PowerLevels, ""),
            ],
        )
        if not self._may_invite(user_id, state):
            return state, (
                403,
                {"msg": "You are not allowed to invite users to this room"},
            )

        # An invited guest has no Matrix invite, so it gets in by asking to join
        join_rules = state.get((EventTypes.JoinRules, ""))
        if join_rules is None or join_rules.content.get("join_rule") not in (
            JoinRules.KNOCK,
            JoinRules.KNOCK_RESTRICTED,
        ):
            return state, (
                403,
                {
                    "msg": "Guests can only be invited to rooms they can ask to join",
                    "reason": "room_not_knockable",
                },
            )

        if room_id in self._config.rooms_forbidden_to_guests:
            return state, (403, {"msg": "Guests are forbidden from this room"})

        return state, None

    @staticmethod
    def _may_invite(user_id: str, state: StateMap[EventBase]) -> bool:
        """Whether this user may invite guests to the room with this state.

        The guests are invited by email rather than by a membership event, so
        nothing else checks this. It mirrors what Synapse requires of a real
        invite: the user is joined to the room and meets its invite power level.
        """
        # A room this server isn't in has no state, not even the create event
        # that `get_user_power_level` asserts
        member = state.get((EventTypes.Member, user_id))
        if (
            member is None
            or member.content.get(EventContentFields.MEMBERSHIP) != Membership.JOIN
        ):
            return False

        return get_user_power_level(user_id, state) >= get_named_level(
            state, "invite", 0
        )


class GuestInviteLinkServlet(GuestInviteServlet):
    """The `POST /_synapse/client/invite_guests/link` endpoint makes a link
    inviting guests to a room, for the caller to share. It requires the
    `room_id` property.

    MAS mints an invite code with no address and no usage limit. Nothing exists
    on this homeserver until someone follows the link, and MAS assigns each
    guest's localpart then.
    """

    async def _async_render_POST(
        self, request: SynapseRequest
    ) -> Tuple[int, Dict[str, Any]]:
        requester = await self._api.get_user_by_req(request)

        json_dict = parse_json_object_from_request(request)

        room_id = json_dict.get("room_id")
        if not isinstance(room_id, str) or not room_id.startswith("!"):
            return 400, {"msg": "You must provide a valid 'room_id'"}

        _, refusal = await self._check_room(requester, room_id)
        if refusal is not None:
            return refusal

        await self._ratelimiter.ratelimit(requester)

        user_id = requester.user.to_string()
        logger.info("'%s' is creating a guest invite link to '%s'", user_id, room_id)
        try:
            token = await self._mas_admin_client.request_admin_token()
            registration_token = await self._mas_admin_client.create_registration_token(
                f"{self._config.user_id_prefix}{{random}}", room_id, token
            )
        # A timeout is a `SynapseError`, and a connection failure a Twisted error
        except Exception:
            logger.exception("Failed to create a guest invite link in MAS")
            return 502, {"msg": "Failed to create the invite link"}

        return 200, {"invite_url": registration_token.invite_url}


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
