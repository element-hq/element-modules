# Copyright 2025, 2026 Element Creations Ltd.
# Copyright 2023 Nordeck IT + Consulting GmbH
# Copyright 2025 New Vector Ltd.
#
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Element-Commercial
# Please see LICENSE files in the project root for full details.
#
# Originally licensed under the Apache License, Version 2.0:
# <http://www.apache.org/licenses/LICENSE-2.0>.

from typing import FrozenSet, Optional

import attr


@attr.s(frozen=True, auto_attribs=True)
class MasConfig:
    admin_api_base_url: str
    oauth_base_url: str
    client_id: str
    client_secret: Optional[str] = None
    client_secret_filepath: Optional[str] = None


@attr.s(frozen=True, auto_attribs=True)
class GuestModuleConfig:
    user_id_prefix: str
    display_name_suffix: str
    enable_user_reaper: bool
    user_expiration_seconds: int
    mas: Optional[MasConfig] = None
    # Whether to monkey-patch RoomListHandler so guests get an empty room directory;
    # see room_list_patch.py for why this defaults to false.
    hide_room_directory_from_guests: bool = False
    # Rooms guests must never be members of, such as an auto-join announcements room.
    # Membership exposes the room's full member list over `/rooms/{roomId}/members`, so
    # a guest in a server-wide room can enumerate every user — what hiding the user
    # directory from guests is meant to prevent.
    # Both invites of guests into these rooms and joins by guests are denied.
    rooms_forbidden_to_guests: FrozenSet[str] = frozenset()
