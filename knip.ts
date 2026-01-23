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
    ],
    workspaces: {
        "modules/*/element-web": {
            entry: "src/index.ts{x,}",
        },
        "packages/element-web-playwright-common": {
            entry: [
                "src/fixtures/index.ts",
                "src/fixtures/services.ts",
                "src/testcontainers/index.ts",
                "src/testcontainers/synapse.ts",
                "src/testcontainers/mas-config.ts",
                "src/stale-screenshot-reporter.ts",
            ],
        },
    },
} satisfies KnipConfig;
