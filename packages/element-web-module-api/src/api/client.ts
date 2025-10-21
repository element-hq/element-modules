/*
Copyright 2025 New Vector Ltd.

SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Element-Commercial
Please see LICENSE files in the repository root for full details.
*/
import type { Room } from "matrix-js-sdk/src/matrix";

/**
 * Modify account data stored on the homeserver.
 * @public
 */
export interface AccountDataApi {
    /**
     * Fetch account data stored from homeserver.
     */
    get(eventType: string): unknown;
    /**
     * Sett account data on the homeserver.
     */
    set(eventType: string, content: unknown): Promise<void>;
    /**
     * Delete account data from homeserver.
     */
    delete(eventType: string): Promise<void>;
}

/**
 * Access some limited functionality from the SDK.
 * @public
 */
export interface ClientApi {
    /**
     * Use this to modify account data on the homeserver.
     */
    getAccountDataApi: () => AccountDataApi;

    /**
     * Fetch room by id from SDK.
     * @param id - Id of the room to get
     * @returns Room object from SDK
     */
    getRoom: (id: string) => Room | null;
}
