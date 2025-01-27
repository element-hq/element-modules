/*
Copyright 2025 New Vector Ltd.

SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Element-Commercial
Please see LICENSE files in the repository root for full details.
*/

// @ts-ignore -- optional interface, will gracefully degrade to `any` if `react-sdk-module-api` isn't installed
import type { ModuleApi, RuntimeModule } from "@matrix-org/react-sdk-module-api";

export type RuntimeModuleConstructor = new (api: ModuleApi) => RuntimeModule;

export interface LegacyModuleApiExtension {
    /**
     * Register a legacy module based on @matrix-org/react-sdk-module-api
     * @param LegacyModule the module class to register
     * @deprecated provided only as a transition path for legacy modules
     */
    _registerLegacyModule(LegacyModule: RuntimeModuleConstructor): Promise<void>;
}
