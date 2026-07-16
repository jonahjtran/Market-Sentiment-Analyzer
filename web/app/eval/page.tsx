import { Scoreboard } from "@/components/Scoreboard";

export const metadata = {
  title: "Benchmark, Cascade",
  description: "Graph RAG vs flat RAG, scored head-to-head on multi-hop questions.",
};

export default function EvalPage() {
  return <Scoreboard />;
}
