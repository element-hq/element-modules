/*
Copyright 2025 New Vector Ltd.

SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Element-Commercial
Please see LICENSE files in the repository root for full details.
*/

/**
 * Exposes certain action that can be performed on element-web.
 * @public
 */
export interface ActionsApi {
    /**
     * Open a room in element-web.
     * @param roomId - id of the room to open
     */
    openRoom: (roomId: string) => void;
}
