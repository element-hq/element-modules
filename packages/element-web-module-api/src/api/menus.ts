import type { MatrixEvent } from "matrix-js-sdk";

export enum MessageMenuTarget {
    TimelineTileContextMenu = "TimelineTileContextMenu",
}

export interface MenuItem {
    label: string;
    icon: string;
    onClick: (closeMenu: () => void) => Promise<void> | void;
}

export interface MenusApi {
    /**
     * Register extra menu items for a message event.
     *
     * This takes a target location, a filter function and a set of items to display.
     *
     * @param target - The target location to render the menu in.
     * @param filter - Filter function to specify which events
     * @param items - The menu items to insert
     */
    registerMessageMenuItems(target: MessageMenuTarget, generateMenu: (ev: MatrixEvent) => MenuItem[]): void;
}
