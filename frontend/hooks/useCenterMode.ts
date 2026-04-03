import { useState } from "react";

export type CenterMode = "chat" | "search";

export function useCenterMode() {
  const [mode, setMode] = useState<CenterMode>("chat");

  function switchToChat() {
    setMode("chat");
  }

  function switchToSearch() {
    setMode("search");
  }

  return { mode, switchToChat, switchToSearch };
}