/*
Copyright 2025 New Vector Ltd.

SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Element-Commercial
Please see LICENSE files in the repository root for full details.
*/

import { type JSX } from "react";

import type { Module, Api, ModuleFactory } from "@element-hq/element-web-module-api";
import { CONFIG_KEY, WidgetTogglesConfig } from "./config";
import { WidgetToggle } from "./toggle";

class WidgetToggleModule implements Module {
    public static readonly moduleApiVersion = "^1.0.0";
    private config?: WidgetTogglesConfig;

    public constructor(private api: Api) {}

    public async load(): Promise<void> {
        try {
            this.config = WidgetTogglesConfig.parse(this.api.config.get(CONFIG_KEY));
        } catch (e) {
            console.error("Failed to init module", e);
            throw new Error(`Errors in module configuration for widget toggles module`);
        }

        this.api.extras.setRoomHeaderButtonCallback((roomId: string) => {
            const widgets = this.api.widget.getWidgetsInRoom(roomId);
            const toggleElements: JSX.Element[] = [];

            for (const widget of widgets) {
                if (this.config?.types.includes(widget.type)) {
                    toggleElements.push(
                        <WidgetToggle
                            app={widget}
                            roomId={roomId}
                            widgetApi={this.api.widget}
                            i18nApi={this.api.i18n}
                        />,
                    );
                }
            }

            if (toggleElements.length === 0) return undefined;
            return <>{toggleElements}</>;
        });
    }
}

export default WidgetToggleModule satisfies ModuleFactory;
