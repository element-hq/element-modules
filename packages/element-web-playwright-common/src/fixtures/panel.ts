/*
 * Copyright 2026 Element Creations Ltd.
 *
 * SPDX-License-Identifier: AGPL-3.0-only OR GPL-3.0-only OR LicenseRef-Element-Commercial
 * Please see LICENSE files in the repository root for full details.
 */
import { test as base } from "./services.js";

export interface TestFixtures {
    /**
     * Whether the left panel should have its width fixed.
     * This is done because the library that we use for rendering collapsible
     * panels uses math to calculate the width which can sometimes leads to +/-1px
     * difference. While this does not matter to the user, it can lead to screenshot
     * tests failing.
     * Defaults to true, should be set to false via {@link base.use} when you want to test the collapse
     * behaviour.
     */
    lockLeftPanelWidth: boolean;
}

export const test = base.extend<TestFixtures>({
    lockLeftPanelWidth: true,
});
