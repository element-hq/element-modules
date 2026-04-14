/*
Copyright 2026 Element Creations Ltd.

SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Element-Commercial
Please see LICENSE files in the repository root for full details.
*/

/**
 * Options provided to the title render function representing the current application state.
 * @public
 */
export type TitleRenderOptions = {
    /**
     * The configured brand name (e.g. "Element", "Element Pro").
     */
    brand: string;
    /**
     * The number of rooms with unread notifications.
     */
    notificationCount?: number;
    /**
     * Whether there is unread activity (but below notification threshold).
     */
    hasActivity?: boolean;
    /**
     * Translated status text from the host application, if applicable
     * (e.g. "Offline"). Undefined when there is no status.
     */
    statusText?: string;
    /**
     * The current room ID, if a room is open.
     */
    roomId?: string;
    /**
     * The current room name, if a room is open.
     */
    roomName?: string;
};

/**
 * Function to render the window title.
 * @public
 * @param opts - Current state of the client.
 * @returns The text to be rendered as the document title.
 */
export type TitleRenderFunction = (opts: TitleRenderOptions) => string;

/**
 * API for modules to customise application branding.
 * @public
 */
export interface BrandApi {
    /**
     * Register a function to render the window title. This function will be called whenever
     * the application needs to re-render the title of the browser window.
     *
     * Only one module may register a title renderer. If another module has already registered
     * one, this will throw.
     *
     * @param renderFunction - The function to use to render the title.
     * @throws If another module has already registered a title renderer.
     */
    registerTitleRenderer(renderFunction: TitleRenderFunction): void;
}
