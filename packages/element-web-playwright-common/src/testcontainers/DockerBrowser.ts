/*
Copyright 2026 Element Creations Ltd.

SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Element-Commercial
Please see LICENSE files in the repository root for full details.
*/

import { GenericContainer, type StartedTestContainer, Wait } from "testcontainers";
import path from "node:path";
import playwrightPkgJson from "@playwright/test/package.json" with { type: "json" };

import { type Logger } from "../utils/logger.js";

/**
 * Utility to manage a playwright server operating just the browser within docker
 * so that playwright client and all the test code can run directly on the host,
 * avoiding nested docker.
 */
export class DockerBrowser {
    private startedContainer?: StartedTestContainer;
    private socatPorts = new Set<number>();

    public constructor(private readonly logger: Logger) {}

    /**
     * The websocket endpoint for playwright-client to connect to for the server
     */
    public get wsEndpoint(): string {
        if (!this.startedContainer) throw new Error("Browser not started");
        return `ws://127.0.0.1:${this.startedContainer.getFirstMappedPort()}/`;
    }

    public async start(): Promise<void> {
        const pwVersion = playwrightPkgJson.version;
        console.info(`Building docker container for playwright ${pwVersion}`);
        const image = await GenericContainer.fromDockerfile(path.join(import.meta.dirname, "..", ".."))
            .withBuildArgs({
                PLAYWRIGHT_VERSION: pwVersion,
            })
            .withCache(true)
            .build(`element-web-playwright-common:${pwVersion}`, { deleteOnExit: false });
        console.info("Docker container built successfully");

        console.info("Starting docker container");
        this.startedContainer = await image
            .withUser("pwuser")
            // Route host.docker.internal to the host for socat to be able to forward the ports
            .withExtraHosts([{ host: "host.docker.internal", ipAddress: "host-gateway" }])
            .withReuse()
            .withAutoRemove(false)
            // Websocket port for playwright-client running on the host to communicate with playwright-server in docker
            .withExposedPorts(3000)
            .withLogConsumer(this.logger.getConsumer("browser"))
            .withWaitStrategy(Wait.forListeningPorts())
            // Run the playwright server
            .withEntrypoint([
                "npx",
                "-y",
                `playwright@${playwrightPkgJson.version}`,
                "run-server",
                "--port=3000",
                "--host=0.0.0.0",
            ])
            .start();
        console.info("Docker container started successfully");
    }

    public async stop(): Promise<void> {
        // We choose to not stop this container to alleviate overheads between test runs
        // Ryuk will clean it up when the tests are over.
    }

    /**
     * Exposes host port as `localhost:$port` within the container hosting the browser
     * @param port the port to expose
     */
    public async exposeHostPort(port: number): Promise<void> {
        if (!this.startedContainer) throw new Error("Browser not started");
        if (this.socatPorts.has(port)) return;
        this.socatPorts.add(port);

        // Run socat inside the container to forward localhost:$PORT -> host.docker.internal:$PORT which maps to the host
        // we cannot simply change the baseURL as then the origin is treated as an unsafe origin due to it not being localhost.
        const prom = this.startedContainer.exec([
            "socat",
            `tcp-listen:${port},fork,reuseaddr`,
            `tcp-connect:host.docker.internal:${port}`,
        ]);

        prom.then((result) => {
            this.logger.writeLog(`socat:${port}`, result.output);
        });
    }
}
