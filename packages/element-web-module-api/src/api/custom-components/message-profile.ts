import { JSX } from "react";
import { MatrixEvent } from "../../models/event";

interface MemberInfo {
    userId: string;
    roomId: string;
    rawDisplayName?: string;
    disambiguate: boolean;
}

/**
 * Properties for all message components.
 * @alpha Subject to change.
 */
export type MessageProfileComponentProps = {
    mxEvent: MatrixEvent;
    onClick?: () => void;
    member?: MemberInfo;
};

/**
 * Function used to render a message profile
 * @alpha Subject to change.
 */
export type MessageProfileRenderFunction = (
    /**
     * Properties for the message to be renderered.
     */
    props: MessageProfileComponentProps,
    /**
     * Render function for the original component.
     */
    originalComponent: (props: MessageProfileComponentProps) => React.JSX.Element,
) => JSX.Element;
