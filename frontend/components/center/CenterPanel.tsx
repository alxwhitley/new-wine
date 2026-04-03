"use client";

import { Message } from "@/hooks/useChat";
import ChatView from "./ChatView";

interface CenterPanelProps {
  messages: Message[];
  chatLoading: boolean;
  chatError: string | null;
  onSendMessage: (message: string) => void;
}

export default function CenterPanel({
  messages,
  chatLoading,
  chatError,
  onSendMessage,
}: CenterPanelProps) {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        flex: 1,
        minWidth: 0,
        minHeight: 0,
        background: "#1f1e1d",
      }}
    >
      <ChatView
        messages={messages}
        loading={chatLoading}
        error={chatError}
        onSend={onSendMessage}
      />
    </div>
  );
}
