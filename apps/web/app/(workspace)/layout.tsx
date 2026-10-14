import { Workspace } from "@/components/workspace";
import { Suspense } from "react";

export default function WorkspaceLayout({ children }: { children: React.ReactNode }) {
  return <Suspense fallback={<div className="loading-state" role="status">Opening AgentScope workspace…</div>}><Workspace>{children}</Workspace></Suspense>;
}
