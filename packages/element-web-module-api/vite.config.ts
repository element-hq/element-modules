/*
Copyright 2025 New Vector Ltd.

SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Element-Commercial
Please see LICENSE files in the repository root for full details.
*/

import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import dts from "vite-plugin-dts";

const __dirname = dirname(fileURLToPath(import.meta.url));

export default defineConfig({
    build: {
        lib: {
            entry: resolve(__dirname, "src/index.ts"),
            name: "element-web-plugin-engine",
            fileName: "element-web-plugin-engine",
        },
        outDir: "lib",
        target: "esnext",
        sourcemap: true,
    },
    plugins: [
        dts({
            rollupTypes: true,
        }),
    ],
    define: {
        __VERSION__: JSON.stringify(process.env.npm_package_version),
    },
});
