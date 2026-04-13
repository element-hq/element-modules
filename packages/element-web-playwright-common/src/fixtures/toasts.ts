/*
 * Copyright 2026 Element Creations Ltd.
 *
 * SPDX-License-Identifier: AGPL-3.0-only OR GPL-3.0-only OR LicenseRef-Element-Commercial
 * Please see LICENSE files in the repository root for full details.
 */

import { type Locator, type Page } from "@playwright/test";

import { test as base } from "./services.js";

// This fixture provides convenient handling of Element Web's toasts.
export const test = base.extend<{
    /**
     * Convenience functions for handling toasts.
     */
    toasts: Toasts;
}>({
    toasts: async ({ page }, use) => {
        const toasts = new Toasts(page);
        await use(toasts);
    },
});

class Toasts {
    public constructor(private readonly page: Page) {}

    /**
     * Find a toast with the given title, if it exists.
     *
     * @param title - title of the toast.
     * @returns the Locator for the matching toast, or an empty locator if it
     *          doesn't exist.
     */
    public getToastIfExists(title: string): Locator {
        return this.page.locator(".mx_Toast_toast", { hasText: title }).first();
    }

    /**
     * Accept a toast with the given title, if it exists. Only works for the
     * first toast in the stack.
     *
     * @param title - title of the toast
     */
    public async acceptToastIfExists(title: string): Promise<void> {
        const toast = this.getToastIfExists(title).locator('.mx_Toast_buttons button[data-kind="primary"]');
        if ((await toast.count()) > 0) {
            await toast.click();
        }
    }

    /**
     * Reject a toast with the given title, if it exists. Only works for the
     * first toast in the stack.
     *
     * @param title - title of the toast
     */
    public async rejectToastIfExists(title: string): Promise<void> {
        const toast = this.getToastIfExists(title).locator('.mx_Toast_buttons button[data-kind="secondary"]');
        if ((await toast.count()) > 0) {
            await toast.click();
        }
    }
}
