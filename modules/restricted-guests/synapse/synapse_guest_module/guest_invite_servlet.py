# Copyright 2026 Element Creations Ltd.
#
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Element-Commercial
# Please see LICENSE files in the project root for full details.

import json
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import quote

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

        emails, refusal = self._parse_emails(json_dict.get("emails"))
        if refusal is not None:
            return refusal

        user_id = requester.user.to_string()
        state, refusal = await self._check_room(requester, room_id)
        if refusal is not None:
            return refusal

        refusal = await self._check_addresses(user_id, room_id, emails)
        if refusal is not None:
            return refusal

        # Last, so that a refused request doesn't spend the limit
        await self._ratelimiter.ratelimit(requester, n_actions=len(emails))

        # A minijinja template, which MAS renders when the guest registers
        username = self._config.user_id_prefix + "{{ random }}"
        expires_at = datetime.fromtimestamp(
            self._api._hs.get_clock().time()
            + self._config.email_invites.invite_lifetime,
            tz=timezone.utc,
        )

        logger.info(
            "'%s' is inviting %d guest(s) to '%s'", user_id, len(emails), room_id
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
                        self._room_url(room_id),
                        token,
                        email=email,
                        usage_limit=1,
                        expires_at=expires_at,
                    )
                    for email in emails
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
                    return _mas_refusal(e, "MAS refused the invites")
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

    def _parse_emails(
        self, emails: Any
    ) -> Tuple[List[str], Optional[Tuple[int, Dict[str, Any]]]]:
        """The addresses, stripped and deduplicated ignoring case, keeping the first
        spelling of each, and the response refusing them if they're malformed or too
        many.
        """
        if (
            not isinstance(emails, list)
            or len(emails) == 0
            or not all(
                isinstance(email, str) and len(email.strip()) > 0 for email in emails
            )
        ):
            return [], (
                400,
                {"msg": "You must provide 'emails' as a non-empty list of strings"},
            )

        # Keyed ignoring case, keeping the first spelling of each address
        unique_emails: Dict[str, str] = {}
        for email in emails:
            unique_emails.setdefault(email.strip().lower(), email.strip())

        max_emails = self._config.email_invites.max_emails
        if len(unique_emails) > max_emails:
            return [], (
                400,
                {"msg": f"You can invite at most {max_emails} emails at once"},
            )

        return list(unique_emails.values()), None

    async def _check_addresses(
        self, user_id: str, room_id: str, emails: List[str]
    ) -> Optional[Tuple[int, Dict[str, Any]]]:
        """The response refusing the request if the user may not invite one of these
        addresses to the room.

        The checks are Synapse's own, as it makes them for email invites.
        """
        for email in emails:
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
        return None

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

    def _room_url(self, room_id: str) -> str:
        """The URL MAS sends an invitee to for this room, once they're signed in.

        MAS redirects to it without reading it, so `client_room_url` can lead to
        any client, or to a page that lets the invitee pick one. Only the room ID
        is filled in: `via` servers, which a client on another homeserver needs
        to find the room, have to be part of `client_room_url`.
        """
        # Checked when the config was parsed
        assert self._config.email_invites.client_room_url is not None
        return self._config.email_invites.client_room_url.replace(
            "{room_id}", quote(room_id, safe="")
        )

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
    `room_id` property, and takes the `emails` allowed to use the link.

    MAS mints an invite code with no usage limit, which only the `emails` can
    use if they're given, and anyone otherwise. Nothing exists on this homeserver
    until someone follows the link, and MAS assigns each guest's localpart then.
    """

    async def _async_render_POST(
        self, request: SynapseRequest
    ) -> Tuple[int, Dict[str, Any]]:
        requester = await self._api.get_user_by_req(request)

        json_dict = parse_json_object_from_request(request)

        room_id = json_dict.get("room_id")
        if not isinstance(room_id, str) or not room_id.startswith("!"):
            return 400, {"msg": "You must provide a valid 'room_id'"}

        emails: Optional[List[str]] = None
        if json_dict.get("emails") is not None:
            emails, refusal = self._parse_emails(json_dict["emails"])
            if refusal is not None:
                return refusal

        user_id = requester.user.to_string()
        _, refusal = await self._check_room(requester, room_id)
        if refusal is not None:
            return refusal

        if emails is not None:
            refusal = await self._check_addresses(user_id, room_id, emails)
            if refusal is not None:
                return refusal

        # One link, however many addresses may use it, because no email is sent
        await self._ratelimiter.ratelimit(requester)

        logger.info("'%s' is creating a guest invite link to '%s'", user_id, room_id)
        token = await self._admin_token()
        if token is None:
            return 502, {"msg": "Failed to create the invite link"}
        try:
            registration_token = await self._mas_admin_client.create_registration_token(
                self._config.user_id_prefix + "{{ random }}",
                self._room_url(room_id),
                token,
                allowed_emails=emails,
            )
        except Exception as e:
            return _mas_failure(e, "Failed to create the invite link")

        if emails is not None and registration_token.allowed_emails is None:
            logger.warning(
                "MAS minted guest invite link '%s' without its allowed addresses: it's "
                "too old to limit who uses a link. Revoke it with MAS's admin API.",
                registration_token.id,
            )
            return 502, {"msg": "Failed to create the invite link"}

        return 200, {
            "id": registration_token.id,
            "invite_url": registration_token.invite_url,
        }

    async def _admin_token(self) -> Optional[str]:
        """An admin access token from MAS, or None if MAS refused or failed it."""
        try:
            return await self._mas_admin_client.request_admin_token()
        # A timeout is a `SynapseError`, and a connection failure a Twisted error
        except Exception:
            logger.exception("Failed to request an admin token from MAS")
            return None


def _non_empty_string(event: Optional[EventBase], key: str) -> Optional[str]:
    """The event's content value for this key, if it's a non-empty string.

    Room members set these, so they can hold anything.
    """
    value = event.content.get(key) if event is not None else None
    return value if isinstance(value, str) and value else None


def _mas_refusal(
    e: HttpResponseException, default_msg: str
) -> Tuple[int, Dict[str, Any]]:
    """A 400 passing on MAS's refusal of a request, with the first title in its error
    body, `{"errors": [{"title"}]}`, or this message.
    """
    try:
        title = json.loads(e.response)["errors"][0]["title"]
    except (ValueError, LookupError, TypeError):
        title = None
    return 400, {"msg": title if isinstance(title, str) and title else default_msg}


def _mas_failure(e: Exception, failure_msg: str) -> Tuple[int, Dict[str, Any]]:
    """The response to a MAS request about a link that raised this: MAS's refusal
    passed on as a 400, and anything else a 502 with this message.
    """
    if isinstance(e, HttpResponseException) and e.code == 400:
        return _mas_refusal(e, "MAS refused the invite link")
    logger.exception(failure_msg)
    return 502, {"msg": failure_msg}
