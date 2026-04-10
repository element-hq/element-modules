/*
Copyright 2025 New Vector Ltd.

SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Element-Commercial
Please see LICENSE files in the repository root for full details.
*/

import { test as base, expect, type TestFixtures } from "@element-hq/element-web-playwright-common";
import { Locator, Page } from "@playwright/test";

export interface Options {
    moduleDir: string;
    modules: string[];
}

export const test = base.extend<TestFixtures & Options & { toasts: Toasts }>({
    moduleDir: ["", { option: true }],
    modules: async ({ moduleDir }, use) => {
        await use([`${moduleDir}/lib/index.js`]);
    },

    page: async ({ page, modules, config }, use) => {
        config.modules = [];
        for (let i = 0; i < modules.length; i++) {
            const module = `/modules/module-${i}/index.js`;
            await page.route(module, async (route) => {
                await route.fulfill({ path: modules[i] });
            });
            config.modules.push(module);
        }

        await use(page);
    },

    toasts: async ({ page }, use) => {
        await use(new Toasts(page));
    },
});

export { expect };

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
