/*
Copyright 2025 New Vector Ltd.

SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Element-Commercial
Please see LICENSE files in the repository root for full details.
*/

import { defineConfig, devices, type Project } from "@playwright/test";
import { globSync } from "glob";
import fs from "node:fs";
import path from "node:path";

import type { Options } from "./playwright/element-web-test";

const baseURL = process.env["BASE_URL"] ?? "http://localhost:8080";

const chromeProject = {
    ...devices["Desktop Chrome"],
    channel: "chromium",
    permissions: ["clipboard-write", "clipboard-read", "microphone"],
    launchOptions: {
        args: ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream", "--mute-audio"],
    },
};

const MODULE_PREFIX = "@element-hq/element-web-module-";

const modulesWithTests = globSync("modules/*/element-web/tests", {});
const moduleProjects = modulesWithTests.map<Project<Options>>((testDir) => {
    const moduleDir = testDir.split("/").slice(0, -1).join("/");
    const packageJson = JSON.parse(fs.readFileSync(path.join(moduleDir, "package.json"), "utf-8"));
    const name = packageJson.name.startsWith(MODULE_PREFIX)
        ? packageJson.name.slice(MODULE_PREFIX.length)
        : packageJson.name;

    return {
        name,
        use: {
            ...chromeProject,
            moduleDir,
        },
        testDir: `${moduleDir}/tests`,
        snapshotDir: `${moduleDir}/tests/snapshots`,
        outputDir: `${moduleDir}/tests/_results`,
    };
});

export default defineConfig<Options>({
    projects: [...moduleProjects],
    use: {
        viewport: { width: 1280, height: 720 },
        ignoreHTTPSErrors: true,
        video: "retain-on-failure",
        baseURL,
        trace: "on-first-retry",
    },
    webServer: {
        command: "docker run --rm -p 8080:80 ghcr.io/element-hq/element-web:v1.11.99",
        url: `${baseURL}/config.json`,
        reuseExistingServer: true,
        timeout: (process.env.CI ? 30 : 120) * 1000,
    },
    workers: 1,
    retries: process.env.CI ? 2 : 0,
    reporter: process.env.CI ? [["html"], ["github"]] : [["html", { outputFolder: "playwright-html-report" }]],
    snapshotPathTemplate: "{snapshotDir}/{testFilePath}/{arg}-{platform}{ext}",
    forbidOnly: !!process.env.CI,
});
