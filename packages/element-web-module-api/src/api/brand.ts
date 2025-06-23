/**
 * Options to be used when rendering a favicon. This represents
 * the state of the application.
 * @public
 */
export type FaviconRenderOptions = {
    /**
     * The number of unread notifications the user has. May be undefined if the notification count isn't known yet (such as during initial loading).
     */
    notificationCount?: number;
    /**
     * Has an error occured (e.g. failure to sync) and should be represented in the favicon's badge.
     */
    errorDidOccur: boolean;
};

/**
 * Options to be used when rendering a favicon. This represents
 * the state of the application.
 * @public
 */
export type TitleRenderOptions = {
    /**
     * The number of unread notifications the user has.
     */
    notificationCount?: number;
    /**
     * Has an error occured (e.g. failure to sync) and should be represented in the favicon's badge.
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
 * Function to render the favicon.
 * @public
 * @param opts - Current state of the client.
 * @returns The URL of the badge to be rendered.
 *          If you are rendering to a canvas, you can use a Data URL here.
 */
export type FaviconRenderFunction = (opts: FaviconRenderOptions) => string;

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
     * Register a function to render a favicon. This function will be called whenever
     * the application needs to re-render the icon.
     * @public
     * @param renderFunction - The function to use to render.
     * @throws If another module has registered a favicon renderer, this will throw.
     */
    registerFaviconRenderer(renderFunction: FaviconRenderFunction): void;

    /**
     * Register a function to render the window title. This function will be called whenever
     * the application needs to re-render the title of the browser window.
     * @public
     * @param renderFunction - The function to use to render.
     * @throws If another module has registered a title renderer, this will throw.
     */
    registerTitleRenderer(renderFunction: TitleRenderFunction): void;
}
