/*
Copyright 2025 New Vector Ltd.

SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Element-Commercial
Please see LICENSE files in the repository root for full details.
*/

declare global {
    // Declare this in the global scope so that it can be overridden with the
    // project's translation keys when used. Ideally, this 'never' declaration
    // would be the default such that any calls would be a type error unless
    // the project provided an override. Unfortunately, vite-plugin-dts doesn't
    // output this declaration into the .d.ts file so TranslationKey is just left
    // as an undefined type which somehow Typescript considers to be totally fine.
    // https://github.com/qmhc/unplugin-dts/issues/419 is a bug about these declarations
    // not being output as of version 4.5.1, but at time of writing we use 4.5.0 and
    // it still doesn't appear.
    type TranslationKey = never;
}

/**
 * The translations for the module.
 * @public
 */
export type Translations = Record<
    TranslationKey,
    {
        [ietfLanguageTag: string]: string;
    }
>;

/**
 * Variables to interpolate into a translation.
 * @public
 */
export type Variables = {
    /**
     * The number of items to count for pluralised translations
     */
    count?: number;
    [key: string]: number | string | undefined;
};

/**
 * The API for interacting with translations.
 * @public
 */
export interface I18nApi {
    /**
     * Read the current language of the user in IETF Language Tag format
     */
    get language(): string;

    /**
     * Register translations for the module, may override app's existing translations
     */
    register(translations: Partial<Translations>): void;

    /**
     * Perform a translation, with optional variables
     * @param key - The key to translate
     * @param variables - Optional variables to interpolate into the translation
     */
    translate(key: keyof Translations, variables?: Variables): string;

    /**
     * Convert a timestamp into a translated, human-readable time,
     * using the current system time as a reference, eg. "5 minutes ago".
     * @param timeMillis - The time in milliseconds since epoch
     */
    humanizeTime(timeMillis: number): string;
}
