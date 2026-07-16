import { Suspense } from "react";
import { GraphExplorer } from "@/components/GraphExplorer";

export const metadata = { title: "Graph explorer, Cascade" };

export default function GraphPage() {
  return (
    <Suspense>
      <GraphExplorer />
    </Suspense>
  );
}
