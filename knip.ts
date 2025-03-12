/*
Copyright 2025 New Vector Ltd.

SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Element-Commercial
Please see LICENSE files in the repository root for full details.
*/

import { KnipConfig } from "knip";

export default {
    ignoreDependencies: [
        // Needed for lint:workflows
        "@action-validator/cli",
        "@action-validator/core",
        // Needed for backwards-compatible types
        "@matrix-org/react-sdk-module-api",
        // Unlisted peer dependency for @matrix-org/react-sdk-module-api
        "matrix-web-i18n",
        // Needed to satisfy the peer dependency of @element-hq/element-web-playwright-common
        "@playwright/test",
        "@element-hq/element-web-module-api",
    ],
    entry: [
        "packages/element-web-playwright-common/src/testcontainers/*",
        "packages/element-web-playwright-common/src/fixtures/services.ts",
    ],
} satisfies KnipConfig;
