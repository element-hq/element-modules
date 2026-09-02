# Copyright 2025, 2026 Element Creations Ltd.
# Copyright 2023 Nordeck IT + Consulting GmbH
# Copyright 2025 New Vector Ltd.
#
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Element-Commercial
# Please see LICENSE files in the project root for full details.
#
# Originally licensed under the Apache License, Version 2.0:
# <http://www.apache.org/licenses/LICENSE-2.0>.

from typing import Tuple
from unittest.mock import Mock

import aiounittest
from parameterized import parameterized_class  # type: ignore[import-untyped]
from synapse.module_api import NOT_SPAM, ProfileInfo, UserProfile, errors
from synapse.module_api.errors import ConfigError
from synapse.types import UserID

from synapse_guest_module.config import GuestModuleConfig, MasConfig
from synapse_guest_module.guest_module import GuestModule
from tests import SQLiteStore, create_module, mas_config_override

FORBIDDEN_ROOM = "!forbidden:matrix.local"


class GuestModuleConfigTest(aiounittest.AsyncTestCase):
    async def test_parse_config_empty(self) -> None:
        config = GuestModule.parse_config({})

        self.assertEqual(
            config,
            GuestModuleConfig(
                user_id_prefix="guest-",
                display_name_suffix=" (Guest)",
                enable_user_reaper=True,
                user_expiration_seconds=24 * 60 * 60,
                mas=None,
            ),
        )

    async def test_parse_config_no_mas(self) -> None:
        config = GuestModule.parse_config(
            {
                "user_id_prefix": "tmp-",
                "display_name_suffix": " (Temporary)",
                "enable_user_reaper": False,
                "user_expiration_seconds": 100,
                "rooms_forbidden_to_guests": ["!forbidden:matrix.local"],
            }
        )

        self.assertEqual(
            config,
            GuestModuleConfig(
                user_id_prefix="tmp-",
                display_name_suffix=" (Temporary)",
                enable_user_reaper=False,
                user_expiration_seconds=100,
                mas=None,
                rooms_forbidden_to_guests=frozenset({"!forbidden:matrix.local"}),
            ),
        )

    async def test_parse_config_mas(self) -> None:
        config = GuestModule.parse_config(
            {
                "mas": {
                    "admin_api_base_url": "https://mas.example.org",
                    "client_id": "client-id",
                    "client_secret": "client-secret",
                },
            }
        )

        self.assertEqual(
            config,
            GuestModuleConfig(
                user_id_prefix="guest-",
                display_name_suffix=" (Guest)",
                enable_user_reaper=True,
                user_expiration_seconds=24 * 60 * 60,
                mas=MasConfig(
                    admin_api_base_url="https://mas.example.org",
                    oauth_base_url="https://mas.example.org",
                    client_id="client-id",
                    client_secret="client-secret",
                    client_secret_filepath=None,
                ),
            ),
        )

    async def test_parse_config_fail_user_id_prefix(self) -> None:
        with self.assertRaisesRegex(
            ConfigError, "Config option 'user_id_prefix' must be a string"
        ):
            GuestModule.parse_config(
                {
                    "user_id_prefix": 1234,
                }
            )

    async def test_parse_config_fail_display_name_suffix(self) -> None:
        with self.assertRaisesRegex(
            ConfigError, "Config option 'display_name_suffix' must be a string"
        ):
            GuestModule.parse_config(
                {
                    "display_name_suffix": 1234,
                }
            )

    async def test_parse_config_fail_enable_user_reaper(self) -> None:
        with self.assertRaisesRegex(
            ConfigError, "Config option 'enable_user_reaper' must be a bool"
        ):
            GuestModule.parse_config(
                {
                    "enable_user_reaper": "False",
                }
            )

    async def test_parse_config_fail_hide_room_directory_from_guests(self) -> None:
        with self.assertRaisesRegex(
            ConfigError,
            "Config option 'hide_room_directory_from_guests' must be a bool",
        ):
            GuestModule.parse_config(
                {
                    "hide_room_directory_from_guests": "False",
                }
            )

    async def test_parse_config_fail_rooms_forbidden_to_guests(self) -> None:
        with self.assertRaisesRegex(
            ConfigError,
            "Config option 'rooms_forbidden_to_guests' must be a list of room IDs",
        ):
            GuestModule.parse_config(
                {
                    "rooms_forbidden_to_guests": ["!room:matrix.local", 1234],
                }
            )

    async def test_parse_config_fail_rooms_forbidden_to_guests_alias(self) -> None:
        with self.assertRaisesRegex(
            ConfigError,
            "Config option 'rooms_forbidden_to_guests' must be a list of room IDs "
            "starting with '!'",
        ):
            GuestModule.parse_config(
                {
                    "rooms_forbidden_to_guests": ["#alias:matrix.local"],
                }
            )

    async def test_parse_config_fail_rooms_forbidden_to_guests_not_a_list(self) -> None:
        with self.assertRaisesRegex(
            ConfigError,
            "Config option 'rooms_forbidden_to_guests' must be a list of room IDs",
        ):
            GuestModule.parse_config(
                {
                    "rooms_forbidden_to_guests": "!room:matrix.local",
                }
            )

    async def test_parse_config_fail_user_expiration_seconds(self) -> None:
        with self.assertRaisesRegex(
            ConfigError, "Config option 'user_expiration_seconds' must be a number"
        ):
            GuestModule.parse_config(
                {
                    "user_expiration_seconds": "1",
                }
            )


@parameterized_class(
    ("variant", "config_override"),
    [
        ("synapse", None),
        ("mas", mas_config_override()),
    ],
)
class GuestModuleRuntimeTest(aiounittest.AsyncTestCase):
    def create_module(self) -> Tuple[GuestModule, Mock, SQLiteStore]:
        return create_module(self.config_override)

    def create_module_with_forbidden_room(
        self,
    ) -> Tuple[GuestModule, Mock, SQLiteStore]:
        config_override = dict(self.config_override or {})
        config_override["rooms_forbidden_to_guests"] = [FORBIDDEN_ROOM]
        return create_module(config_override)

    async def test_profile_update_no_guest(self) -> None:
        module, module_api, _ = self.create_module()

        await module.profile_update(
            "@my-user:matrix.local",
            ProfileInfo(display_name="My User", avatar_url=None),
            True,
            False,
        )

        module_api.set_displayname.assert_not_called()

    async def test_profile_update_guest_keep(self) -> None:
        module, module_api, _ = self.create_module()

        await module.profile_update(
            "@guest-asdf:matrix.local",
            ProfileInfo(display_name="My User (Guest)", avatar_url=None),
            True,
            False,
        )

        module_api.set_displayname.assert_not_called()

    async def test_profile_update_guest_add_and_trim(self) -> None:
        module, module_api, _ = self.create_module()

        await module.profile_update(
            "@guest-asdf:matrix.local",
            ProfileInfo(display_name="My User ", avatar_url=None),
            True,
            False,
        )

        module_api.set_displayname.assert_awaited_once_with(
            UserID.from_string("@guest-asdf:matrix.local"),
            "My User (Guest)",
        )

    async def test_callback_user_may_create_room_no_guest(self) -> None:
        module, _, _ = self.create_module()

        allow = await module.callback_user_may_create_room(
            "@my-user:matrix.local",
        )

        self.assertTrue(allow)

    async def test_callback_user_may_create_room_guest(self) -> None:
        module, _, _ = self.create_module()

        allow = await module.callback_user_may_create_room(
            "@guest-asdf:matrix.local",
        )

        self.assertFalse(allow)

    async def test_callback_user_may_invite_no_guest(self) -> None:
        module, _, _ = self.create_module()

        allow = await module.callback_user_may_invite(
            "@inviter:matrix.local",
            "@my-user:matrix.local",
            "!room:matrix.local",
        )

        self.assertTrue(allow)

    async def test_callback_user_may_invite_guest(self) -> None:
        module, _, _ = self.create_module()

        allow = await module.callback_user_may_invite(
            "@guest-asdf:matrix.local",
            "@inviter:matrix.local",
            "!room:matrix.local",
        )

        self.assertFalse(allow)

    async def test_callback_user_may_invite_remote_guest_lookalike(self) -> None:
        module, _, _ = self.create_module()

        # A federated invite reaches this callback with a remote sender; a remote
        # `@guest-*` user is not one of ours.
        allow = await module.callback_user_may_invite(
            "@guest-asdf:other.local",
            "@my-user:matrix.local",
            "!room:matrix.local",
        )

        self.assertTrue(allow)

    async def test_callback_user_may_invite_guest_into_forbidden_room(self) -> None:
        module, _, _ = self.create_module_with_forbidden_room()

        allow = await module.callback_user_may_invite(
            "@my-user:matrix.local",
            "@guest-asdf:matrix.local",
            FORBIDDEN_ROOM,
        )

        self.assertFalse(allow)

    async def test_callback_user_may_invite_no_guest_into_forbidden_room(self) -> None:
        module, _, _ = self.create_module_with_forbidden_room()

        allow = await module.callback_user_may_invite(
            "@my-user:matrix.local",
            "@my-other-user:matrix.local",
            FORBIDDEN_ROOM,
        )

        self.assertTrue(allow)

    async def test_callback_user_may_invite_guest_inviter_in_forbidden_room(
        self,
    ) -> None:
        module, _, _ = self.create_module_with_forbidden_room()

        allow = await module.callback_user_may_invite(
            "@guest-asdf:matrix.local",
            "@my-user:matrix.local",
            FORBIDDEN_ROOM,
        )

        self.assertFalse(allow)

    async def test_callback_user_may_invite_guest_into_other_room(self) -> None:
        module, _, _ = self.create_module_with_forbidden_room()

        allow = await module.callback_user_may_invite(
            "@my-user:matrix.local",
            "@guest-asdf:matrix.local",
            "!room:matrix.local",
        )

        self.assertTrue(allow)

    async def test_callback_user_may_join_room_guest_forbidden_room_invited(
        self,
    ) -> None:
        module, _, _ = self.create_module_with_forbidden_room()

        result = await module.callback_user_may_join_room(
            "@guest-asdf:matrix.local", FORBIDDEN_ROOM, True
        )

        self.assertEqual(result, errors.Codes.FORBIDDEN)

    async def test_callback_user_may_join_room_guest_forbidden_room_not_invited(
        self,
    ) -> None:
        module, module_api, _ = self.create_module_with_forbidden_room()

        result = await module.callback_user_may_join_room(
            "@guest-asdf:matrix.local", FORBIDDEN_ROOM, False
        )

        self.assertEqual(result, errors.Codes.FORBIDDEN)
        # The room's join rules are never consulted: a forbidden room is refused even
        # if it is a knock room.
        module_api.get_state_events_in_room.assert_not_called()

    async def test_callback_user_may_join_room_no_guest_forbidden_room(self) -> None:
        module, _, _ = self.create_module_with_forbidden_room()

        result = await module.callback_user_may_join_room(
            "@my-user:matrix.local", FORBIDDEN_ROOM, False
        )

        self.assertEqual(result, NOT_SPAM)

    async def test_callback_user_may_join_room_no_guest_forbidden_room_invited(
        self,
    ) -> None:
        module, _, _ = self.create_module_with_forbidden_room()

        result = await module.callback_user_may_join_room(
            "@my-user:matrix.local", FORBIDDEN_ROOM, True
        )

        self.assertEqual(result, NOT_SPAM)

    async def test_callback_user_may_join_room_guest_other_room_invited(self) -> None:
        module, _, _ = self.create_module_with_forbidden_room()

        result = await module.callback_user_may_join_room(
            "@guest-asdf:matrix.local", "!room:matrix.local", True
        )

        self.assertEqual(result, NOT_SPAM)

    async def test_callback_check_username_for_spam_no_guest(self) -> None:
        module, _, _ = self.create_module()

        hidden = await module.callback_check_username_for_spam(
            UserProfile(
                user_id="@my-user:matrix.local",
                display_name=None,
                avatar_url=None,
            ),
            "@my-other-user:matrix.local",
        )

        self.assertFalse(hidden)

    async def test_callback_check_username_for_spam_guest(self) -> None:
        module, _, _ = self.create_module()

        hidden = await module.callback_check_username_for_spam(
            UserProfile(
                user_id="@guest-asdf:matrix.local",
                display_name=None,
                avatar_url=None,
            ),
            "@my-user:matrix.local",
        )

        self.assertTrue(hidden)

    async def test_callback_check_username_for_spam_remote_guest_lookalike(
        self,
    ) -> None:
        module, _, _ = self.create_module()

        hidden = await module.callback_check_username_for_spam(
            UserProfile(
                user_id="@guest-asdf:other.local",
                display_name=None,
                avatar_url=None,
            ),
            "@my-user:matrix.local",
        )

        self.assertFalse(hidden)

    async def test_callback_check_username_for_spam_guest_requester(self) -> None:
        module, _, _ = self.create_module()

        hidden = await module.callback_check_username_for_spam(
            UserProfile(
                user_id="@my-user:matrix.local",
                display_name=None,
                avatar_url=None,
            ),
            "@guest-asdf:matrix.local",
        )

        self.assertTrue(hidden)

    async def test_callback_check_username_for_spam_remote_guest_lookalike_requester(
        self,
    ) -> None:
        module, _, _ = self.create_module()

        hidden = await module.callback_check_username_for_spam(
            UserProfile(
                user_id="@my-user:matrix.local",
                display_name=None,
                avatar_url=None,
            ),
            "@guest-asdf:other.local",
        )

        self.assertFalse(hidden)
