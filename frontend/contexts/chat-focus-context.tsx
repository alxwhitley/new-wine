"use client";

import { createContext, useContext, useState } from "react";

interface ChatFocusContextValue {
  inputFocused: boolean;
  setInputFocused: (v: boolean) => void;
}

const ChatFocusContext = createContext<ChatFocusContextValue>({
  inputFocused: false,
  setInputFocused: () => {},
});

export function ChatFocusProvider({ children }: { children: React.ReactNode }) {
  const [inputFocused, setInputFocused] = useState(false);
  return (
    <ChatFocusContext.Provider value={{ inputFocused, setInputFocused }}>
      {children}
    </ChatFocusContext.Provider>
  );
}

export function useChatFocus() {
  return useContext(ChatFocusContext);
}
