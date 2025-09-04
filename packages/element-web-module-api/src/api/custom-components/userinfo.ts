import { JSX } from "react";

/**
 * @alpha Subject to change.
 */
export type UserInfoComponentProps = {
    userId: string;
};

/**
 * Function used to render a message profile
 * @alpha Subject to change.
 */
export type UserInfoRenderFunction = (
    /**
     * Properties for the message to be renderered.
     */
    props: UserInfoComponentProps,
    /**
     * Render function for the original component. This may be omitted if the message would not normally be rendered.
     */
    originalComponent: (props: UserInfoComponentProps) => React.JSX.Element,
) => JSX.Element;
