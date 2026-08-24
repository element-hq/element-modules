# Copyright 2026 Element Creations Ltd.
#
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Element-Commercial
# Please see LICENSE files in the project root for full details.

import inspect
from typing import Any, Dict, Optional
from unittest.mock import Mock

import aiounittest
import attr
from synapse.logging.context import ContextRequest, LoggingContext
from synapse.module_api import ModuleApi
from synapse.module_api.errors import ConfigError
from synapse.types import UserID

from synapse_guest_module.room_list_patch import (
    PATCHED_METHODS,
    patch_room_list_handler,
)
from tests import StubRoomListHandler, create_module, stub_homeserver

SERVER_NAME = "matrix.local"
GUEST = "@guest-abc:matrix.local"
USER = "@alice:matrix.local"
REMOTE_GUEST = "@guest-abc:other.example"
EMPTY_ROOM_LIST = {"chunk": [], "total_room_count_estimate": 0}


def is_guest(user_id: str) -> bool:
    user = UserID.from_string(user_id)
    return user.domain == SERVER_NAME and user.localpart.startswith("guest-")


def logging_context(requester: Optional[str]) -> LoggingContext:
    request = ContextRequest(
        request_id="req-1",
        ip_address="1.2.3.4",
        site_tag="test",
        requester=requester,
        authenticated_entity=requester,
        method="GET",
        url="/_matrix/client/v3/publicRooms",
        protocol="1.1",
        user_agent="test",
    )
    return LoggingContext(name="test", server_name=SERVER_NAME, request=request)


def patched_handler(
    handler: Any = None,
    allow_public_rooms_without_auth: bool = False,
) -> Any:
    api = Mock(spec=ModuleApi)
    api._hs = stub_homeserver(handler, allow_public_rooms_without_auth)
    patch_room_list_handler(api, is_guest)
    return api._hs.get_room_list_handler()


class RoomListPatchTest(aiounittest.AsyncTestCase):
    async def test_guest_gets_an_empty_local_room_list(self) -> None:
        handler = patched_handler()

        with logging_context(GUEST):
            result = await handler.get_local_public_room_list(limit=10)

        self.assertEqual(result, EMPTY_ROOM_LIST)
        self.assertEqual(handler.calls, [])

    async def test_guest_gets_an_empty_remote_room_list(self) -> None:
        handler = patched_handler()

        with logging_context(GUEST):
            result = await handler.get_remote_public_room_list("other.example")

        self.assertEqual(result, EMPTY_ROOM_LIST)
        self.assertEqual(handler.calls, [])

    async def test_the_empty_room_list_is_not_shared_between_requests(self) -> None:
        """Guards against returning a shared module-level literal a caller could
        mutate."""
        handler = patched_handler()

        with logging_context(GUEST):
            first = await handler.get_local_public_room_list()
            first["chunk"].append("mutated")
            second = await handler.get_local_public_room_list()

        self.assertEqual(second, EMPTY_ROOM_LIST)

    async def test_ordinary_user_is_passed_through(self) -> None:
        handler = patched_handler()

        with logging_context(USER):
            result = await handler.get_local_public_room_list(
                10, "since-token", search_filter={"generic_search_term": "a"}
            )

        self.assertIs(result, handler.result)
        self.assertEqual(
            handler.calls,
            [
                (
                    "get_local_public_room_list",
                    (10, "since-token"),
                    {"search_filter": {"generic_search_term": "a"}},
                )
            ],
        )

    async def test_the_sentinel_context_is_passed_through(self) -> None:
        """Background jobs run outside any request context."""
        handler = patched_handler()

        result = await handler.get_local_public_room_list()

        self.assertIs(result, handler.result)

    async def test_federation_origin_is_passed_through(self) -> None:
        handler = patched_handler()

        with logging_context("other.example"):
            result = await handler.get_local_public_room_list()

        self.assertIs(result, handler.result)

    async def test_unauthenticated_request_is_passed_through(self) -> None:
        handler = patched_handler()

        with logging_context(None):
            result = await handler.get_local_public_room_list()

        self.assertIs(result, handler.result)

    async def test_unparsable_requester_is_passed_through(self) -> None:
        handler = patched_handler()

        with logging_context("@not-a-user-id"):
            result = await handler.get_local_public_room_list()

        self.assertIs(result, handler.result)

    async def test_remote_guest_is_passed_through(self) -> None:
        handler = patched_handler()

        with logging_context(REMOTE_GUEST):
            result = await handler.get_local_public_room_list()

        self.assertIs(result, handler.result)

    async def test_patching_twice_does_not_stack_wrappers(self) -> None:
        handler = StubRoomListHandler()
        patched_handler(handler)
        patched_handler(handler)

        with logging_context(GUEST):
            empty = await handler.get_local_public_room_list()

        with logging_context(USER):
            passed_through = await handler.get_local_public_room_list()

        self.assertEqual(empty, EMPTY_ROOM_LIST)
        self.assertIs(passed_through, handler.result)
        self.assertEqual(len(handler.calls), 1)
        # Unwrapping once reaches the stub itself, so only one wrapper was installed.
        wrapper = handler.__dict__["get_local_public_room_list"]
        self.assertIs(
            wrapper.__wrapped__.__func__,
            StubRoomListHandler.get_local_public_room_list,
        )

    async def test_refuses_allow_public_rooms_without_auth(self) -> None:
        with self.assertRaises(ConfigError):
            patched_handler(allow_public_rooms_without_auth=True)

    async def test_nothing_is_patched_when_public_rooms_are_unauthenticated(
        self,
    ) -> None:
        handler = StubRoomListHandler()

        with self.assertRaises(ConfigError):
            patched_handler(handler, allow_public_rooms_without_auth=True)

        self.assertNotIn("get_local_public_room_list", handler.__dict__)

    async def test_refuses_a_handler_missing_a_method(self) -> None:
        class HandlerWithoutRemote:
            async def get_local_public_room_list(self) -> Dict[str, Any]:
                return {}

        with self.assertRaises(ConfigError):
            patched_handler(HandlerWithoutRemote())

    async def test_refuses_a_method_that_is_not_a_coroutine_function(self) -> None:
        class SyncHandler(StubRoomListHandler):
            def get_remote_public_room_list(  # type: ignore[override]
                self, *args: Any, **kwargs: Any
            ) -> Dict[str, Any]:
                return {}

        with self.assertRaises(ConfigError):
            patched_handler(SyncHandler())

    async def test_nothing_is_patched_when_a_method_is_unsupported(self) -> None:
        class SyncHandler(StubRoomListHandler):
            def get_remote_public_room_list(  # type: ignore[override]
                self, *args: Any, **kwargs: Any
            ) -> Dict[str, Any]:
                return {}

        handler = SyncHandler()

        with self.assertRaises(ConfigError):
            patched_handler(handler)

        # The patcher installs wrappers as instance attributes.
        self.assertNotIn("get_local_public_room_list", handler.__dict__)

    async def test_the_patched_internals_still_exist_in_the_installed_synapse(
        self,
    ) -> None:
        """Fails in CI when the installed Synapse moves the internals the patch
        replaces."""
        from synapse.handlers.room_list import RoomListHandler

        for name in PATCHED_METHODS:
            self.assertTrue(
                inspect.iscoroutinefunction(getattr(RoomListHandler, name, None)),
                f"RoomListHandler.{name}",
            )
        self.assertIn("requester", attr.fields_dict(ContextRequest))


class GuestModuleRoomListPatchWiringTest(aiounittest.AsyncTestCase):
    """Checks that `GuestModule.__init__` applies the patch. `RoomListPatchTest`
    covers the patch's behaviour."""

    async def test_patched_when_hide_room_directory_from_guests_is_enabled(
        self,
    ) -> None:
        _, module_api, _ = create_module({"hide_room_directory_from_guests": True})

        handler = module_api._hs.get_room_list_handler()
        self.assertIn("get_local_public_room_list", handler.__dict__)

    async def test_not_patched_by_default(self) -> None:
        _, module_api, _ = create_module()

        handler = module_api._hs.get_room_list_handler()
        self.assertNotIn("get_local_public_room_list", handler.__dict__)
