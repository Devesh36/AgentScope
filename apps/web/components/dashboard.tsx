"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import dynamic from "next/dynamic";
import { Empty } from "./common";
import { Button } from "./ui/button";

const loading = () => <div className="panel empty" role="status">Loading workspace…</div>;
const Overview = dynamic(() => import("./overview").then((page) => page.Overview), { loading });
const AgentsPage = dynamic(() => import("./telemetry-pages").then((page) => page.AgentsPage), { loading });
const AgentDetail = dynamic(() => import("./telemetry-pages").then((page) => page.AgentDetail), { loading });
const RunsPage = dynamic(() => import("./telemetry-pages").then((page) => page.RunsPage), { loading });
const RunDetail = dynamic(() => import("./telemetry-pages").then((page) => page.RunDetail), { loading });
const IncidentsPage = dynamic(() => import("./incident-pages").then((page) => page.IncidentsPage), { loading });
const IncidentDetail = dynamic(() => import("./incident-pages").then((page) => page.IncidentDetail), { loading });
const InvestigationsPage = dynamic(() => import("./incident-pages").then((page) => page.InvestigationsPage), { loading });
const InvestigationDetail = dynamic(() => import("./incident-pages").then((page) => page.InvestigationDetail), { loading });
const SettingsPage = dynamic(() => import("./settings-pages").then((page) => page.SettingsPage), { loading });
const SimulationPage = dynamic(() => import("./settings-pages").then((page) => page.SimulationPage), { loading });

export function Dashboard() {
  const segments = usePathname().split("/").filter(Boolean);
  if (segments[0] === "agents")
    return segments[1] ? <AgentDetail id={segments[1]} /> : <AgentsPage />;
  if (segments[0] === "runs")
    return segments[1] ? <RunDetail id={segments[1]} /> : <RunsPage />;
  if (segments[0] === "incidents")
    return segments[1] ? (
      <IncidentDetail id={segments[1]} />
    ) : (
      <IncidentsPage />
    );
  if (segments[0] === "investigations")
    return segments[1] ? (
      <InvestigationDetail id={segments[1]} />
    ) : (
      <InvestigationsPage />
    );
  if (segments[0] === "settings") return <SettingsPage />;
  if (segments[0] === "simulation") return <SimulationPage />;
  if (segments.length && !(segments.length === 1 && segments[0] === "dashboard"))
    return (
      <Empty
        title="Page not found"
        description="This page doesn’t exist in your workspace."
        action={
          <Button asChild>
            <Link href="/dashboard">Back to overview</Link>
          </Button>
        }
      />
    );
  return <Overview />;
}
