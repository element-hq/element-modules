# Copyright 2026 Element Creations Ltd.
#
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Element-Commercial
# Please see LICENSE files in the project root for full details.

import io
from typing import Any, Dict, Optional, Tuple, cast
from unittest.mock import Mock

import aiounittest
from synapse.http.site import SynapseRequest
from twisted.web.test.requesthelper import DummyRequest

from synapse_guest_module import GuestModule
from tests import SQLiteStore, create_module, mas_config_override

ROOM_ID = "!room:matrix.local"
INVITER = "@inviter:matrix.local"


def state_event(content: Dict[str, Any]) -> Mock:
    event = Mock()
    event.content = content
    return event


def room_state(
    membership: Optional[str] = "join",
    power_levels: Optional[Dict[str, Any]] = None,
) -> Dict[Tuple[str, str], Mock]:
    state = {}
    if membership is not None:
        state[("m.room.member", INVITER)] = state_event({"membership": membership})
    if power_levels is not None:
        state[("m.room.power_levels", "")] = state_event(power_levels)
    return state


class GuestInviteServletTest(aiounittest.AsyncTestCase):
    def create_module(self) -> Tuple[GuestModule, Mock, SQLiteStore]:
        module, module_api, store = create_module(mas_config_override())

        requester = Mock()
        requester.user.to_string.return_value = INVITER

        module_api.get_user_by_req.return_value = requester
        module_api.get_room_state.return_value = room_state()
        module_api.http_client.post_urlencoded_get_json.return_value = {
            "access_token": "mas_admin_token"
        }
        module_api.http_client.post_json_get_json.return_value = {"scheduled": 2}

        return module, module_api, store

    async def render(
        self,
        module: GuestModule,
        body: bytes = (
            b'{"room_id":"!room:matrix.local","emails":["alice@example.com"]}'
        ),
    ) -> Tuple[int, Any]:
        servlet = module.invite_servlet
        assert servlet is not None
        request = cast(SynapseRequest, DummyRequest([]))
        request.content = io.BytesIO(body)
        return await servlet._async_render_POST(request)

    async def test_no_servlet_without_mas(self) -> None:
        module, _, _ = create_module()

        self.assertIsNone(module.invite_servlet)

    async def test_missing_room_id(self) -> None:
        module, _, _ = self.create_module()

        status, response = await self.render(
            module, b'{"emails":["alice@example.com"]}'
        )

        self.assertEqual(status, 400)

    async def test_missing_emails(self) -> None:
        module, _, _ = self.create_module()

        status, response = await self.render(
            module, b'{"room_id":"!room:matrix.local"}'
        )

        self.assertEqual(status, 400)

    async def test_not_in_room(self) -> None:
        module, module_api, _ = self.create_module()
        module_api.get_room_state.return_value = room_state(None)

        status, response = await self.render(module)

        self.assertEqual(status, 403)
        module_api.http_client.post_json_get_json.assert_not_called()

    async def test_below_invite_power_level(self) -> None:
        module, module_api, _ = self.create_module()
        module_api.get_room_state.return_value = room_state(power_levels={"invite": 50})

        status, response = await self.render(module)

        self.assertEqual(status, 403)
        module_api.http_client.post_json_get_json.assert_not_called()

    async def test_success(self) -> None:
        module, module_api, _ = self.create_module()
        module_api.get_room_state.return_value = room_state(
            power_levels={"invite": 50, "users": {INVITER: 100}}
        )

        status, response = await self.render(
            module,
            b'{"room_id":"!room:matrix.local",'
            b'"emails":["alice@example.com"," bob@example.com "]}',
        )

        self.assertEqual(status, 202)
        self.assertEqual(response, {"scheduled": 2})

        module_api.http_client.post_json_get_json.assert_called_once()
        body = module_api.http_client.post_json_get_json.call_args.kwargs["post_json"]
        self.assertEqual(body["room_id"], ROOM_ID)
        self.assertEqual(
            [invite["email"] for invite in body["invites"]],
            ["alice@example.com", "bob@example.com"],
        )
        # Each recipient is pinned to a guest localpart of their own
        usernames = [invite["username"] for invite in body["invites"]]
        for username in usernames:
            self.assertRegex(username, r"^guest-[a-z0-9]{32}$")
        self.assertEqual(len(set(usernames)), 2)
