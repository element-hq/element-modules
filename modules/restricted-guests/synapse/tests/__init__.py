# Copyright 2025, 2026 Element Creations Ltd.
# Copyright 2023 Nordeck IT + Consulting GmbH
# Copyright 2025 New Vector Ltd.
#
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Element-Commercial
# Please see LICENSE files in the project root for full details.
#
# Originally licensed under the Apache License, Version 2.0:
# <http://www.apache.org/licenses/LICENSE-2.0>.

import sqlite3
from asyncio import Future
from typing import Any, Awaitable, Callable, Dict, List, Tuple, TypeVar, Union
from unittest.mock import Mock

from synapse.http.client import SimpleHttpClient
from synapse.module_api import ModuleApi
from synapse.types import DomainSpecificString

from synapse_guest_module import GuestModule

RV = TypeVar("RV")
TV = TypeVar("TV")

SERVER_NAME = "matrix.local"


class SQLiteStore:
    """In-memory SQLite store. We can't just use a run_db_interaction function that opens
    its own connection, since we need to use the same connection for all queries in a
    test.
    """

    def __init__(self) -> None:
        self.conn = sqlite3.connect(":memory:")

    async def run_db_interaction(
        self, desc: str, f: Callable[..., RV], *args: Any, **kwargs: Any
    ) -> RV:
        cur = CursorWrapper(self.conn.cursor())
        try:
            res = f(cur, *args, **kwargs)
            self.conn.commit()
            return res
        except Exception:
            self.conn.rollback()
            raise


class CursorWrapper:
    """Wrapper around a SQLite cursor."""

    def __init__(self, cursor: sqlite3.Cursor) -> None:
        self.cur = cursor

    def execute(self, sql: str, args: Any) -> None:
        self.cur.execute(sql, args)

    @property
    def rowcount(self) -> Any:
        return self.cur.rowcount

    def fetchone(self) -> Any:
        return self.cur.fetchone()

    def fetchall(self) -> Any:
        return self.cur.fetchall()

    def __iter__(self) -> Any:
        return self.cur.__iter__()

    def __next__(self) -> Any:
        return self.cur.__next__()


def make_awaitable(result: TV) -> Awaitable[TV]:
    """
    Makes an awaitable, suitable for mocking an `async` function.
    This uses Futures as they can be awaited multiple times so can be returned
    to multiple callers.
    This function has been copied directly from Synapse's tests code.
    """
    future = Future()  # type: ignore
    future.set_result(result)
    return future


def get_qualified_user_id(username: str) -> str:
    return f"@{username}:matrix.local"


def is_mine(id: Union[str, DomainSpecificString]) -> bool:
    """Mirrors `ModuleApi.is_mine`: a parsed ID compares its domain, and a raw string
    goes through `HomeServer.is_mine_id`, which returns False rather than raising on a
    malformed ID."""
    if isinstance(id, DomainSpecificString):
        return id.domain == SERVER_NAME
    localpart_hostname = id.split(":", 1)
    if len(localpart_hostname) < 2:
        return False
    return localpart_hostname[1] == SERVER_NAME


async def register_user(localpart: str, admin: bool = False) -> str:
    return f"@{localpart}:matrix.local"


class StubRoomListHandler:
    """Stand-in for Synapse's `RoomListHandler`.

    `patch_room_list_handler` only reaches for the two methods it replaces, and requires
    them to be coroutine functions.
    """

    def __init__(self) -> None:
        self.calls: List[Tuple[str, Tuple[Any, ...], Dict[str, Any]]] = []
        self.result: Dict[str, Any] = {
            "chunk": [{"room_id": "!room:matrix.local"}],
            "total_room_count_estimate": 1,
        }

    async def get_local_public_room_list(
        self, *args: Any, **kwargs: Any
    ) -> Dict[str, Any]:
        self.calls.append(("get_local_public_room_list", args, kwargs))
        return self.result

    async def get_remote_public_room_list(
        self, *args: Any, **kwargs: Any
    ) -> Dict[str, Any]:
        self.calls.append(("get_remote_public_room_list", args, kwargs))
        return self.result


def stub_homeserver(
    handler: Any = None,
    allow_public_rooms_without_auth: bool = False,
) -> Mock:
    """A stub for `ModuleApi._hs`, which `Mock(spec=ModuleApi)` does not provide because
    it is an instance attribute.
    """
    hs = Mock()
    hs.config.server.allow_public_rooms_without_auth = allow_public_rooms_without_auth
    hs.get_room_list_handler.return_value = (
        StubRoomListHandler() if handler is None else handler
    )
    return hs


def create_module(
    config_override: Dict[str, Any] | None = None,
) -> Tuple[GuestModule, Mock, SQLiteStore]:
    store = SQLiteStore()
    _setup_db(store.conn)

    client = Mock(spec=SimpleHttpClient)
    client.post_json_get_json.return_value = make_awaitable(None)

    # Create a mock based on the ModuleApi spec, but override some mocked functions
    # because some capabilities are needed for running the tests.
    module_api = Mock(spec=ModuleApi)
    module_api._hs = stub_homeserver()
    module_api.http_client = client
    module_api.server_name = SERVER_NAME
    module_api.public_baseurl = "https://matrix.local:1234/"
    module_api.run_db_interaction.side_effect = store.run_db_interaction
    module_api.get_qualified_user_id.side_effect = get_qualified_user_id
    module_api.is_mine.side_effect = is_mine
    module_api.check_user_exists.return_value = make_awaitable(False)
    module_api.register_user.side_effect = register_user
    module_api.register_device.return_value = make_awaitable(
        ("DEVICEID", "syn_registered_token", None, None)
    )

    # If necessary, give parse_config some configuration to parse.
    config_dict: Dict[str, Any] = {
        "enable_user_reaper": False,
    }
    if config_override is not None:
        config_dict.update(config_override)

    config = GuestModule.parse_config(config_dict)

    module = GuestModule(config, module_api)

    if getattr(module, "_mas_tables_ready", None) is not None:
        module._mas_tables_ready.set()  # type: ignore[union-attr]

    return module, module_api, store


def mas_config_override() -> Dict[str, Any]:
    return {
        "mas": {
            "admin_api_base_url": "https://mas.example.org",
            "oauth_base_url": "https://oauth.mas.example.org",
            "client_id": "client-id",
            "client_secret": "client-secret",
        },
    }


def _setup_db(conn: sqlite3.Connection) -> None:
    conn.execute("CREATE TABLE access_tokens(user_id text, token text)")
    conn.execute(
        "CREATE TABLE users(name text, deactivated smallint, creation_ts bigint)"
    )
    conn.execute(
        "CREATE TABLE guest_module_mas_users(mas_user_id text, user_id text, created_at_sec bigint)"
    )
