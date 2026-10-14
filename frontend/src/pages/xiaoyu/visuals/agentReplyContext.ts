import { createContext, useContext } from 'react';

/** Context for reply-type action cards to trigger a chat message send */
export const AgentReplyContext = createContext<{ onReply?: (value: string) => void }>({});
export const useAgentReply = () => useContext(AgentReplyContext);
