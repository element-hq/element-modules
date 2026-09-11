# Copyright 2025, 2026 Element Creations Ltd.
# Copyright 2023 Nordeck IT + Consulting GmbH
# Copyright 2025 New Vector Ltd.
#
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Element-Commercial
# Please see LICENSE files in the project root for full details.
#
# Originally licensed under the Apache License, Version 2.0:
# <http://www.apache.org/licenses/LICENSE-2.0>.

import asyncio
import logging
from typing import Any, Dict, Literal, Optional, Tuple, Union

from synapse.module_api import (
    NOT_SPAM,
    LoggingTransaction,
    ModuleApi,
    ProfileInfo,
    UserProfile,
    errors,
    run_as_background_process,
)
from synapse.module_api.errors import ConfigError
from synapse.types import UserID

from synapse_guest_module.config import GuestModuleConfig, MasConfig
from synapse_guest_module.guest_registration_servlet import GuestRegistrationServlet
from synapse_guest_module.guest_user_reaper import GuestUserReaper
from synapse_guest_module.mas_admin_client import MasAdminClient
from synapse_guest_module.room_list_patch import patch_room_list_handler

logger = logging.getLogger("synapse.contrib." + __name__)


class GuestModule:
    def __init__(self, config: GuestModuleConfig, api: ModuleApi):
        self._api = api
        self._config = config
        self._mas_tables_ready: asyncio.Event | None = None

        if config.hide_room_directory_from_guests:
            patch_room_list_handler(api, self._is_module_guest)

        mas_admin_client = (
            MasAdminClient(api, config.mas) if config.mas is not None else None
        )
        if config.mas is not None:
            self._mas_tables_ready = asyncio.Event()
            run_as_background_process(
                "guest_module_mas_db_init",
                self._init_mas_tables,
                bg_start_span=False,
            )
        self.registration_servlet = GuestRegistrationServlet(
            config, api, mas_admin_client, self._mas_tables_ready
        )
        self._api.register_web_resource(
            "/_synapse/client/register_guest", self.registration_servlet
        )
        self._api.register_third_party_rules_callbacks(
            on_profile_update=self.profile_update
        )
        self._api.register_spam_checker_callbacks(
            user_may_create_room=self.callback_user_may_create_room,
            user_may_invite=self.callback_user_may_invite,
            user_may_join_room=self.callback_user_may_join_room,
            check_username_for_spam=self.callback_check_username_for_spam,
        )

        # Start the user reaper
        self.reaper = GuestUserReaper(
            api, config, mas_admin_client, self._mas_tables_ready
        )
        if config.enable_user_reaper:
            run_as_background_process(
                "guest_module_reaper_bg_task",
                self.reaper.run,
                bg_start_span=False,
            )

    def _is_module_guest(self, user_id: str) -> bool:
        """Whether this user is a guest managed by this module.

        Guests are registered by this module, so only a local user can be one; a remote
        user whose localpart happens to start with the prefix is not ours. Raises on a
        string that is not a valid user ID.
        """
        user = UserID.from_string(user_id)
        return self._api.is_mine(user) and user.localpart.startswith(
            self._config.user_id_prefix
        )

    @staticmethod
    def parse_config(config: Dict[str, Any]) -> GuestModuleConfig:
        """Parse the module configuration"""

        user_id_prefix = config.get("user_id_prefix", "guest-")
        if not isinstance(user_id_prefix, str):
            raise ConfigError("Config option 'user_id_prefix' must be a string")

        display_name_suffix = config.get("display_name_suffix", " (Guest)")
        if not isinstance(display_name_suffix, str):
            raise ConfigError("Config option 'display_name_suffix' must be a string")

        enable_user_reaper = config.get("enable_user_reaper", True)
        if not isinstance(enable_user_reaper, bool):
            raise ConfigError("Config option 'enable_user_reaper' must be a bool")

        user_expiration_seconds = config.get(
            "user_expiration_seconds",
            24 * 60 * 60,
        )
        if not isinstance(user_expiration_seconds, int):
            raise ConfigError(
                "Config option 'user_expiration_seconds' must be a number"
            )

        hide_room_directory_from_guests = config.get(
            "hide_room_directory_from_guests", False
        )
        if not isinstance(hide_room_directory_from_guests, bool):
            raise ConfigError(
                "Config option 'hide_room_directory_from_guests' must be a bool"
            )

        rooms_forbidden_to_guests = config.get("rooms_forbidden_to_guests", [])
        if not isinstance(rooms_forbidden_to_guests, list):
            raise ConfigError(
                "Config option 'rooms_forbidden_to_guests' must be a list of room IDs"
            )

        for room_id in rooms_forbidden_to_guests:
            # Aliases are rejected rather than resolved: `auto_join_rooms`, the option
            # this one usually mirrors, takes aliases only, so an alias copied across
            # would match no room and let guests in silently.
            if not isinstance(room_id, str) or not room_id.startswith("!"):
                raise ConfigError(
                    "Config option 'rooms_forbidden_to_guests' must be a list of room "
                    f"IDs starting with '!', got {room_id!r}"
                )

        mas_config = config.get("mas")
        mas: Optional[MasConfig] = None
        if mas_config is not None:
            if not isinstance(mas_config, dict):
                raise ConfigError("Config option 'mas' must be an object")

            admin_api_base_url = mas_config.get("admin_api_base_url")
            if (
                not isinstance(admin_api_base_url, str)
                or len(admin_api_base_url.strip()) == 0
            ):
                raise ConfigError(
                    "Config option 'mas.admin_api_base_url' is required and must be a string"
                )

            oauth_base_url = mas_config.get("oauth_base_url", admin_api_base_url)
            if not isinstance(oauth_base_url, str) or len(oauth_base_url.strip()) == 0:
                raise ConfigError("Config option 'mas.oauth_base_url' must be a string")

            client_id = mas_config.get("client_id")
            if not isinstance(client_id, str) or len(client_id.strip()) == 0:
                raise ConfigError(
                    "Config option 'mas.client_id' is required and must be a string"
                )

            client_secret = mas_config.get("client_secret")
            if client_secret is not None:
                if (
                    not isinstance(client_secret, str)
                    or len(client_secret.strip()) == 0
                ):
                    raise ConfigError(
                        "Config option 'mas.client_secret' must be a string"
                    )
                client_secret = client_secret.strip()

            client_secret_filepath = mas_config.get("client_secret_filepath")
            if client_secret_filepath is not None:
                if (
                    not isinstance(client_secret_filepath, str)
                    or len(client_secret_filepath.strip()) == 0
                ):
                    raise ConfigError(
                        "Config option 'mas.client_secret_filepath' must be a string"
                    )
                client_secret_filepath = client_secret_filepath.strip()

            if client_secret is None and client_secret_filepath is None:
                raise ConfigError(
                    "Config option 'mas.client_secret' or 'mas.client_secret_filepath' is required"
                )

            if client_secret is not None and client_secret_filepath is not None:
                raise ConfigError(
                    "Config option 'mas.client_secret' and 'mas.client_secret_filepath' are mutually exclusive"
                )

            mas = MasConfig(
                admin_api_base_url.strip(),
                oauth_base_url.strip(),
                client_id.strip(),
                client_secret,
                client_secret_filepath,
            )

        return GuestModuleConfig(
            user_id_prefix,
            display_name_suffix,
            enable_user_reaper,
            user_expiration_seconds,
            mas,
            hide_room_directory_from_guests,
            frozenset(rooms_forbidden_to_guests),
        )

    async def profile_update(
        self,
        user_id: str,
        new_profile: ProfileInfo,
        by_admin: bool,
        deactivation: bool,
    ) -> None:
        """Is called whenever a profile is updated. We check that a guest user
        always contains the configured suffix (default ` (Guest)`) and add it if
        it is missing.
        """
        user_is_guest = self._is_module_guest(user_id)
        if user_is_guest:
            new_profile_display_name = (
                "" if new_profile.display_name is None else new_profile.display_name
            )
            guest_display_name_not_valid = not new_profile_display_name.endswith(
                self._config.display_name_suffix
            )
            if guest_display_name_not_valid:
                user_id_1 = UserID.from_string(user_id)
                guest_display_name = (
                    new_profile_display_name.strip() + self._config.display_name_suffix
                )
                await self._api.set_displayname(user_id_1, guest_display_name)

    async def _init_mas_tables(self) -> None:
        if self._mas_tables_ready is None:
            return

        try:
            await self._api.run_db_interaction(
                "guest_module_create_mas_tables",
                self._create_mas_tables,
            )
        except Exception as err:
            logger.error("Failed to initialize MAS tables: %s", err)
        finally:
            self._mas_tables_ready.set()

    @staticmethod
    def _create_mas_tables(txn: LoggingTransaction) -> None:
        txn.execute(
            """
            CREATE TABLE IF NOT EXISTS guest_module_mas_users (
                mas_user_id TEXT PRIMARY KEY NOT NULL,
                user_id TEXT NOT NULL,
                created_at_sec BIGINT NOT NULL
            )
            """,
            (),
        )
        txn.execute(
            """
            CREATE INDEX IF NOT EXISTS guest_module_mas_users_created_at_sec
            ON guest_module_mas_users (created_at_sec)
            """,
            (),
        )

    async def callback_user_may_create_room(
        self,
        user_id: str,
    ) -> bool:
        """Returns whether this user is allowed to create a room. Guest users
        should not be able to do that.
        """
        user_is_guest = self._is_module_guest(user_id)
        return not user_is_guest

    async def callback_user_may_invite(
        self,
        inviter: str,
        invitee: str,
        room_id: str,
    ) -> bool:
        """Returns whether this user is allowed to invite someone into a room.
        Guest users may not invite anyone, and nobody may invite a guest into a room
        that is forbidden to guests.

        Server admins bypass spam-checker callbacks entirely; the join check is what
        enforces the forbidden-room property. Federated invites reach this callback
        too, through Synapse's `federated_user_may_invite` fallback.
        """
        if self._is_module_guest(inviter):
            return False

        if self._is_module_guest(invitee):
            return room_id not in self._config.rooms_forbidden_to_guests

        return True

    async def callback_user_may_join_room(
        self, user_id: str, room_id: str, is_invited: bool
    ) -> Union[
        Literal["NOT_SPAM"], errors.Codes, Tuple[errors.Codes, Dict[str, Any]], bool
    ]:
        """Returns whether this user is allowed to join a room. Guest users
        should only be able to do that if the room is Ask to Join (knock), and never
        for a room that is forbidden to guests.

        A forbidden room is refused even when `is_invited` is set: Synapse invites a
        newly-registered user from `auto_join_user_id` before joining them to an
        invite-only `auto_join_rooms` room, so honouring the invite here would let
        every guest straight in.
        """
        user_is_guest = self._is_module_guest(user_id)
        if user_is_guest and room_id in self._config.rooms_forbidden_to_guests:
            return errors.Codes.FORBIDDEN

        if not user_is_guest or is_invited:
            return NOT_SPAM

        join_rules_events = await self._api.get_state_events_in_room(
            room_id, [("m.room.join_rules", None)]
        )
        if join_rules_events is None or len(list(join_rules_events)) == 0:
            return errors.Codes.BAD_STATE

        for event in join_rules_events:
            join_rule = event.get("content", {})
            is_knock = join_rule.get("join_rule").startswith("knock")
            if user_is_guest and is_knock:
                return NOT_SPAM

        return errors.Codes.FORBIDDEN

    async def callback_check_username_for_spam(
        self, user_profile: UserProfile, requester_id: str
    ) -> bool:
        """Returns whether to hide this profile from the user directory. Guests are
        hidden from everybody, and guests are shown an empty directory.

        The two-parameter signature is the contract with Synapse: it dispatches this
        callback by arity, and only passes `requester_id` to a two-parameter one.
        """
        # Native Matrix guests never reach this callback, since the user directory
        # servlet rejects them, so matching the prefix identifies every requester that
        # must be given an empty directory.
        #
        # `limited` is computed from the SQL LIMIT before Synapse filters on this
        # callback, so a guest can get `limited: true` alongside an empty result list.
        # Clients render that as an ordinary empty result.
        if self._is_module_guest(requester_id):
            return True

        return self._is_module_guest(user_profile["user_id"])
