/*
Copyright 2025 New Vector Ltd.

SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Element-Commercial
Please see LICENSE files in the repository root for full details.
*/

/**
 * Options to be used when rendering the window title. This represents
 * the state of the application.
 * @public
 */
export type TitleRenderOptions = {
    /**
     * The number of unread notifications the user has.
     */
    notificationCount?: number;
    /**
     * Has an error occured (e.g. failure to sync).
     */
    errorDidOccur?: boolean;
    /**
     * The current room ID, if one is open.
     */
    roomId?: string;
    /**
     * The current room name, if one is open.
     */
    roomName?: string;

    /**
     * Does the user have notifications enabled globally.
     */
    notificationsEnabled?: boolean;
};

/**
 * Function to render the window title.
 * @public
 * @param opts - Current state of the client.
 * @returns The text to be rendered.
 */
export type TitleRenderFunction = (opts: TitleRenderOptions) => string;

/**
 * @public
 */
export interface BrandApi {
    /**
     * Register a function to render the window title. This function will be called whenever
     * the application needs to re-render the title of the browser window.
     * @public
     * @param renderFunction - The function to use to render.
     * @throws If another module has registered a title renderer, this will throw.
     */
    registerTitleRenderer(renderFunction: TitleRenderFunction): void;
}
