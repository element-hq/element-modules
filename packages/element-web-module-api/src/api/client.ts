/*
Copyright 2025 New Vector Ltd.

SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Element-Commercial
Please see LICENSE files in the repository root for full details.
*/

import type { Room } from "../models/Room";
import type { MatrixEvent } from "../models/event";
import { type Watchable } from "./watchable";

/**
 * Modify account data stored on the homeserver.
 * @public
 */
export interface AccountDataApi {
    /**
     * Returns a watchable with account data for this event type.
     */
    get(eventType: string): Watchable<unknown>;
    /**
     * Set account data on the homeserver.
     */
    set(eventType: string, content: unknown): Promise<void>;
    /**
     * Changes the content of this event to be empty.
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
    accountData: AccountDataApi;

    /**
     * Fetch room by id from SDK.
     * @param id - Id of the room to get
     * @returns Room object from SDK
     */
    getRoom: (id: string) => Room | null;

    /**
     * Download the body of an `mxc://` URI via the authenticated media
     * endpoint, returning the raw text. Use for small text/JSON/XML media
     * (e.g. policy files) referenced by state events.
     */
    downloadMxc: (mxcUrl: string) => Promise<string>;

    /**
     * Upload content to the media repository, returning the mxc:// URI.
     *
     * @param content - The content to upload (Blob or File).
     * @param contentType - The MIME type of the content (e.g. "application/xml").
     * @returns The mxc:// URI of the uploaded content.
     */
    uploadContent: (content: Blob | File, contentType?: string) => Promise<string>;

    /**
     * Send a state event to a room.
     *
     * @param roomId - The room to send the event to.
     * @param eventType - The type of state event.
     * @param content - The event content.
     * @param stateKey - The state key (defaults to "").
     */
    sendStateEvent: (
        roomId: string,
        eventType: string,
        content: Record<string, unknown>,
        stateKey?: string,
    ) => Promise<void>;

    /**
     * Register a listener for state events in rooms. The callback is invoked
     * whenever a state event is received or updated in any room.
     *
     * @param callback - Called with the state event.
     * @returns A function that removes the listener when called.
     */
    onStateEvent: (callback: (event: MatrixEvent) => void) => () => void;
}
