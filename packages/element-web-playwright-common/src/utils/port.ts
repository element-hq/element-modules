/*
Copyright 2024-2025 New Vector Ltd.
Copyright 2022 The Matrix.org Foundation C.I.C.

SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Element-Commercial
Please see LICENSE files in the repository root for full details.
*/

import * as net from "node:net";

/**
 * Get a free networking port on the system.
 */
export async function getFreePort(): Promise<number> {
    return new Promise<number>((resolve) => {
        const srv = net.createServer();
        srv.listen(0, () => {
            const port = (<net.AddressInfo>srv.address()).port;
            srv.close(() => resolve(port));
        });
    });
}
