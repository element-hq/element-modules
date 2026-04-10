/*
Copyright 2025 New Vector Ltd.

SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Element-Commercial
Please see LICENSE files in the repository root for full details.
*/

import { type JSX } from "react";

/**
 * Properties of an item added to the Space panel
 * @alpha
 */
export interface SpacePanelItemProps {
    /**
     * A CSS class name for the item
     */
    className?: string;

    /**
     * An icon to show in the item. If not provided, no icon will be shown.
     */
    icon?: JSX.Element;

    /**
     * The label to show in the item
     */
    label: string;

    /**
     * A tooltip to show when hovering over the item
     */
    tooltip?: string;

    /**
     * Styles to apply to the item
     */
    style?: React.CSSProperties;

    /**
     * Callback when the item is selected
     */
    onSelected: () => void;
}

/**
 * A callback that returns a JSX element representing the buttons.
 *
 * @alpha
 * @param roomId - The ID of the room for which the header is being rendered.
 * @returns A JSX element representing the buttons to be rendered in the room header, or undefined if no buttons should be rendered.
 */
export type RoomHeaderButtonsCallback = (roomId: string) => JSX.Element | undefined;

/**
 * A callback that returns a JSX element representing a banner to display below the room header.
 *
 * @alpha
 * @param roomId - The ID of the room for which the banner is being rendered.
 * @returns A JSX element representing the banner, or undefined if no banner should be rendered.
 */
export type RoomBannerCallback = (roomId: string) => JSX.Element | undefined;

/**
 * A callback that returns a JSX element to display to the left of the composer input.
 *
 * @alpha
 * @param roomId - The ID of the room for which the composer is being rendered.
 * @returns A JSX element to render in the composer, or undefined if nothing should be rendered.
 */
export type ComposerLeftComponentCallback = (roomId: string) => JSX.Element | undefined;

/**
 * A callback that can modify event content before it is sent.
 *
 * @alpha
 * @param roomId - The ID of the room the event is being sent to.
 * @param content - The event content that is about to be sent. May be mutated in place.
 * @returns The (possibly modified) event content to send.
 */
export type EventContentTransformCallback = (
    roomId: string,
    content: Record<string, unknown>,
) => Record<string, unknown>;

/**
 * API for inserting extra UI into Element Web.
 * @alpha Subject to change.
 */
export interface ExtrasApi {
    /**
     * Inserts an item into the space panel as if it were a space button, below
     * buttons for other spaces.
     * If called again with the same spaceKey, will update the existing item.
     * @param spaceKey - A key to identify this space-like item.
     * @param props - Properties of the item to add.
     */
    setSpacePanelItem(spaceKey: string, props: SpacePanelItemProps): void;

    /**
     * Registers a callback to get the list of visible rooms for a given space.
     *
     * Element Web will call this callback when checking if a room is displayed for the given space. For example in case of message editing or replying.
     * If the space added by the module displays a room view and doesn't provide this callback, Element Web won't be able to determine if a room is visible in that space and will redirect to display the room in its vanilla space/metaspace.
     *
     * @param spaceKey - The space key to get visible rooms for.
     * @param cb - A callback that returns the list of visible room IDs.
     */
    getVisibleRoomBySpaceKey(spaceKey: string, cb: () => string[]): void;

    /**
     * Adds a callback to get extra buttons in the room header (which can vary depending on the room being displayed).
     *
     * @param cb - A callback that returns a JSX element representing the buttons (see {@link RoomHeaderButtonsCallback}).
     */
    addRoomHeaderButtonCallback(cb: RoomHeaderButtonsCallback): void;

    /**
     * Adds a callback to get a banner element to display below the room header in the room view.
     *
     * @param cb - A callback that returns a JSX element representing the banner (see {@link RoomBannerCallback}).
     */
    addRoomBannerCallback(cb: RoomBannerCallback): void;

    /**
     * Adds a callback to render a component to the left of the message composer input.
     *
     * @param cb - A callback that returns a JSX element (see {@link ComposerLeftComponentCallback}).
     */
    addComposerLeftComponentCallback(cb: ComposerLeftComponentCallback): void;

    /**
     * Adds a callback to transform event content before it is sent.
     * Multiple callbacks will be applied in registration order.
     *
     * @param cb - A callback that receives and returns event content (see {@link EventContentTransformCallback}).
     */
    addEventContentTransformCallback(cb: EventContentTransformCallback): void;

    /**
     * Adds a callback to transform the unencrypted envelope of encrypted events before they are sent.
     * This allows modules to add fields to the outer `m.room.encrypted` event content alongside the ciphertext.
     * Multiple callbacks will be applied in registration order.
     *
     * @param cb - A callback that receives and returns event content (see {@link EventContentTransformCallback}).
     */
    addEncryptedEnvelopeTransformCallback(cb: EventContentTransformCallback): void;
}
