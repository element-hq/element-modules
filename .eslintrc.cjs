module.exports = {
    plugins: ["matrix-org", "eslint-plugin-react-compiler"],
    extends: ["plugin:matrix-org/typescript", "plugin:matrix-org/react", "plugin:matrix-org/a11y"],
    parserOptions: {
        project: ["./tsconfig.json"],
    },
    env: {
        browser: true,
        node: true,
    },
    rules: {
        "react/jsx-key": ["error"],

        "no-restricted-properties": [
            "error",
            ...buildRestrictedPropertiesOptions(
                ["window.innerHeight", "window.innerWidth", "window.visualViewport"],
                "Use UIStore to access window dimensions instead.",
            ),
            ...buildRestrictedPropertiesOptions(
                ["*.mxcUrlToHttp", "*.getHttpUriForMxc"],
                "Use Media helper instead to centralise access for customisation.",
            ),
            ...buildRestrictedPropertiesOptions(["window.setImmediate"], "Use setTimeout instead."),
        ],
        "no-restricted-globals": [
            "error",
            {
                name: "setImmediate",
                message: "Use setTimeout instead.",
            },
            {
                name: "Buffer",
                message: "Buffer is not available in the web.",
            },
        ],

        "import/no-duplicates": ["error"],
        "matrix-org/require-copyright-header": "error",

        "react-compiler/react-compiler": "error",
    },
    settings: {
        react: {
            version: "detect",
        },
    },
};

function buildRestrictedPropertiesOptions(properties, message) {
    return properties.map((prop) => {
        let [object, property] = prop.split(".");
        if (object === "*") {
            object = undefined;
        }
        return {
            object,
            property,
            message,
        };
    });
}
