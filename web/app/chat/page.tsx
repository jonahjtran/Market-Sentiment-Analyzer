import { Suspense } from "react";
import { ChatScreen } from "@/components/ChatScreen";

export const metadata = { title: "Analyst, Cascade" };

export default function ChatPage() {
  return (
    <Suspense>
      <ChatScreen />
    </Suspense>
  );
}
