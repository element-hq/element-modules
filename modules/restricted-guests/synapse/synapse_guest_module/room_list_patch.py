# Copyright 2026 Element Creations Ltd.
#
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Element-Commercial
# Please see LICENSE files in the project root for full details.

import functools
import inspect
import logging
from typing import Any, Callable, Coroutine

import attr

# The logging context is not part of the module API surface; reading the requester
# from it is the same private-internals reach as the patch itself.
from synapse.logging.context import ContextRequest, current_context
from synapse.module_api import JsonDict, ModuleApi, UserID
from synapse.module_api.errors import ConfigError, SynapseError

logger = logging.getLogger("synapse.contrib." + __name__)

RoomListMethod = Callable[..., Coroutine[Any, Any, JsonDict]]

# `ResponseCache` memoises the inner `_get_public_room_list`, so on a cache hit the
# inner call ran in the first caller's logging context. Only these outer methods are
# guaranteed to run in the context of the request being served.
PATCHED_METHODS = ("get_local_public_room_list", "get_remote_public_room_list")

_PATCH_MARKER = "_guest_module_room_list_patched"


def _requester_is_guest(is_module_guest: Callable[[str], bool]) -> bool:
    """Whether the request being served belongs to a guest managed by this module.

    `PublicRoomListRestServlet` authenticates the request but does not pass the
    `Requester` to the handler. The `SynapseRequest.requester` setter copies the MXID
    into `logcontext.request.requester` before the servlet runs, so the logging
    context still identifies the caller.
    """
    request = current_context().request
    # The sentinel context: anything not serving an HTTP request, such as background
    # jobs and startup. No guest is waiting on the result, so pass it through.
    if request is None:
        return False

    # `requester` holds a bare server name for inbound federation and `None` for
    # unauthenticated requests; neither can be a local guest.
    requester = request.requester
    if not isinstance(requester, str) or not requester.startswith("@"):
        return False

    try:
        UserID.from_string(requester)
    except SynapseError:
        # Not a parsable user ID, so not one of ours.
        return False

    # Match only guests this module created. /publicRooms allows native Synapse
    # guests (allow_guest=True); those pass through, and the login flow that creates
    # them does not exist under MAS.
    return is_module_guest(requester)


def _guard(
    original: RoomListMethod, is_module_guest: Callable[[str], bool]
) -> RoomListMethod:
    @functools.wraps(original)
    async def wrapper(*args: Any, **kwargs: Any) -> JsonDict:
        if _requester_is_guest(is_module_guest):
            # What Synapse serves when enable_room_list_search is disabled. A persistent
            # 403 sends Element X Android into a retry loop instead of an empty state.
            return {"chunk": [], "total_room_count_estimate": 0}

        return await original(*args, **kwargs)

    setattr(wrapper, _PATCH_MARKER, True)
    return wrapper


def patch_room_list_handler(
    api: ModuleApi, is_module_guest: Callable[[str], bool]
) -> None:
    """Make the room directory look empty to guests.

    Synapse offers no module callback on the room list, so this reassigns private
    internals, verified against Synapse 1.159.

    The checks below catch a renamed or re-shaped `RoomListHandler` and a
    `ContextRequest` that has lost its `requester` field. They cannot catch
    `SynapseRequest.requester` no longer writing the MXID into that field before the
    servlet runs, nor it writing something that is not an MXID string: both leave the
    field present but empty, and both fail open.
    """
    hs = api._hs

    if hs.config.server.allow_public_rooms_without_auth:
        raise ConfigError(
            "The guest module requires 'allow_public_rooms_without_auth' to be false: "
            "the room directory is otherwise served without an access token, leaving "
            "no requester to hide it from"
        )

    if not any(field.name == "requester" for field in attr.fields(ContextRequest)):
        raise ConfigError(
            "This version of Synapse is not supported by the guest module: the logging "
            "context request has no 'requester' field"
        )

    handler = hs.get_room_list_handler()
    for name in PATCHED_METHODS:
        if not inspect.iscoroutinefunction(getattr(handler, name, None)):
            raise ConfigError(
                "This version of Synapse is not supported by the guest module: "
                f"RoomListHandler.{name} is missing or is not a coroutine function"
            )

    for name in PATCHED_METHODS:
        original = getattr(handler, name)
        if getattr(original, _PATCH_MARKER, False):
            # A second module instance in the same process would otherwise stack
            # another wrapper on the first one's.
            logger.warning(
                "RoomListHandler.%s is already patched by another module instance; "
                "keeping that wrapper",
                name,
            )
            continue
        setattr(handler, name, _guard(original, is_module_guest))

    logger.warning(
        "Patched RoomListHandler.{%s} to hide the room directory from guests",
        ", ".join(PATCHED_METHODS),
    )
