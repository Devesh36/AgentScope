"use client";
import { createContext, useContext, useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  QueryClient,
  QueryClientProvider,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import {
  Activity,
  ArrowUpRight,
  BookOpen,
  Bot,
  ChevronDown,
  FlaskConical,
  LayoutDashboard,
  Menu,
  Search,
  Settings2,
  ShieldAlert,
  Sparkles,
  Waypoints,
  X,
  Check,
  AlertCircle,
  RefreshCw,
} from "lucide-react";
import type { Project } from "@/lib/types";
import { Button } from "./ui/button";

type Context = {
  project: string;
  setProject: (id: string) => void;
  projects: Project[];
  hours: number;
  setHours: (v: number) => void;
  source: string;
  setSource: (v: string) => void;
  notify: (message: string, error?: boolean) => void;
  connected: boolean;
};
const Ctx = createContext<Context | null>(null);
export function useWorkspace() {
  const value = useContext(Ctx);
  if (!value) throw Error("Workspace provider is required");
  return value;
}
export async function request<T>(
  path: string,
  project: string,
  options?: RequestInit,
): Promise<T> {
  const response = await fetch(`/api/v1/${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(project ? { "X-Project-ID": project } : {}),
      ...options?.headers,
    },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw Error(
      typeof body.detail === "string"
        ? body.detail
        : `Request failed (${response.status}). Check your input and try again.`,
    );
  }
  return response.status === 204 ? (undefined as T) : response.json();
}
export function useData<T>(path: string, enabled = true) {
  const { project } = useWorkspace();
  return useQuery<T, Error>({
    queryKey: [project, path],
    queryFn: () => request<T>(path, project),
    enabled: Boolean(project) && enabled,
    refetchInterval: 15000,
  });
}
export function useAction() {
  const { project, notify } = useWorkspace();
  const query = useQueryClient();
  const [pending, setPending] = useState(false);
  async function act<T>(
    path: string,
    body: unknown = {},
    message = "Changes saved",
    method = "POST",
  ): Promise<T | undefined> {
    setPending(true);
    try {
      const result = await request<T>(path, project, {
        method,
        body: method === "DELETE" ? undefined : JSON.stringify(body),
      });
      await query.invalidateQueries();
      if (message) notify(message);
      return result;
    } catch (e) {
      notify(e instanceof Error ? e.message : "Request failed", true);
      return undefined;
    } finally {
      setPending(false);
    }
  }
  return { act, pending };
}
const nav = [
  ["Overview", "/dashboard", LayoutDashboard],
  ["Agents", "/agents", Bot],
  ["Run explorer", "/runs", Waypoints],
  ["Incident center", "/incidents", ShieldAlert],
  ["Investigations", "/investigations", Sparkles],
  ["Simulation lab", "/simulation", FlaskConical],
] as const;
export function Workspace({ children }: { children: React.ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: { staleTime: 2000, retry: 1, refetchOnWindowFocus: true },
        },
      }),
  );
  return (
    <QueryClientProvider client={client}>
      <Shell>{children}</Shell>
    </QueryClientProvider>
  );
}
function Shell({ children }: { children: React.ReactNode }) {
  const [project, setProjectState] = useState("");
  const [hours, setHours] = useState(24);
  const [source, setSource] = useState("all");
  const [mobile, setMobile] = useState(false);
  const [connected, setConnected] = useState(false);
  const [toast, setToast] = useState<{
    message: string;
    error: boolean;
  } | null>(null);
  const path = usePathname();
  const client = useQueryClient();
  const projectsQuery = useQuery({
    queryKey: ["projects"],
    queryFn: () => request<Project[]>("projects", ""),
    retry: 1,
  });
  const projects = projectsQuery.data || [];
  useEffect(() => {
    if (projects.length && !projects.some((p) => p.id === project)) {
      const saved = localStorage.getItem("agentscope-project");
      const requested = new URLSearchParams(window.location.search).get("project");
      const selected = projects.some((p) => p.id === requested) ? requested! : projects.some((p) => p.id === saved) ? saved! : projects[0].id;
      setProjectState(selected);
      localStorage.setItem("agentscope-project", selected);
    }
  }, [projects, project]);
  useEffect(() => {
    if (!project) return;
    let events: EventSource;
    let retry: ReturnType<typeof setTimeout> | undefined;
    let delay = 1000;
    let active = true;
    const refresh = () => client.invalidateQueries({ predicate: (q) => q.queryKey[0] === project });
    const connect = () => {
      if (!active) return;
      events = new EventSource(`/api/v1/events?project_id=${encodeURIComponent(project)}`);
      events.onopen = () => {
        if (!active) return;
        delay = 1000;
        setConnected(true);
        refresh();
      };
      events.onerror = () => {
        if (!active) return;
        setConnected(false);
        // Some HTTP failures permanently close EventSource. Recreate it with
        // bounded backoff; each successful reconnect reads the persisted state.
        events.close();
        retry = setTimeout(connect, delay);
        delay = Math.min(delay * 2, 10000);
      };
      events.addEventListener("refresh", () => {
        if (!active) return;
        setConnected(true);
        refresh();
      });
    };
    connect();
    return () => {
      active = false;
      if (retry) clearTimeout(retry);
      events.close();
      setConnected(false);
    };
  }, [project, client]);
  useEffect(() => {
    setMobile(false);
  }, [path]);
  useEffect(() => {
    if (!toast) return;
    const id = setTimeout(() => setToast(null), toast.error ? 8000 : 4000);
    return () => clearTimeout(id);
  }, [toast]);
  const setProject = (id: string) => {
    setProjectState(id);
    localStorage.setItem("agentscope-project", id);
  };
  const current = [...nav, ["Settings", "/settings", Settings2] as const].find(
    (n) => path.startsWith(n[1]),
  );
  return (
    <Ctx.Provider
      value={{
        project,
        setProject,
        projects,
        hours,
        setHours,
        source,
        setSource,
        connected,
        notify: (message, error = false) => setToast({ message, error }),
      }}
    >
      <div className="app-shell">
        {mobile && (
          <button
            className="mobile-overlay"
            onClick={() => setMobile(false)}
            aria-label="Close navigation"
          />
        )}
        <aside className={`sidebar ${mobile ? "open" : ""}`}>
          <Link href="/" className="brand">
            <span className="brand-mark">
              <Activity size={20} />
            </span>
            AgentScope
            <span className="brand-dot" />
          </Link>
          <div className="workspace-switch">
            <span className="workspace-avatar">AS</span>
            <div>
              <strong>AgentScope workspace</strong>
              <span>Local development</span>
            </div>
            <ChevronDown size={14} />
          </div>
          <div className="nav-label">WORKSPACE</div>
          <nav>
            {nav.map(([name, href, Icon]) => (
              <Link
                href={href}
                key={href}
                className={`nav-item ${path.startsWith(href) ? "active" : ""}`}
              >
                <Icon size={17} />
                <span>{name}</span>
                {name === "Simulation lab" && (
                  <span className="nav-tag">DEMO</span>
                )}
              </Link>
            ))}
          </nav>
          <div className="sidebar-bottom">
            <div className="sidebar-note">
              <span className="eyebrow">
                <span
                  className={`status-dot ${connected ? "green" : "amber"}`}
                />{" "}
                {connected ? "LIVE TELEMETRY UPDATES" : "READY TO CONNECT"}
              </span>
              <strong>Every run tells a story.</strong>
              <p>Follow the traces. Find the signal.</p>
              <Link href="/simulation">
                Explore the simulation lab <ArrowUpRight size={13} />
              </Link>
            </div>
            <a
              className="nav-item"
              href="https://github.com/Devesh36/AgentScope"
              target="_blank"
              rel="noreferrer"
            >
              <BookOpen size={17} />
              Repository
              <ArrowUpRight size={13} />
            </a>
            <Link
              href="/settings"
              className={`nav-item ${path.startsWith("/settings") ? "active" : ""}`}
            >
              <Settings2 size={17} />
              Settings
            </Link>
            <div className="user">
              <span className="user-avatar">D</span>
              <div>
                <strong>Developer</strong>
                <span>Local workspace</span>
              </div>
              <span className="version">v0.1</span>
            </div>
          </div>
        </aside>
        <div className="main-shell">
          <header className="topbar">
            <div className="topbar-left">
              <Button
                className="mobile-menu"
                variant="ghost"
                onClick={() => setMobile(!mobile)}
                aria-label="Toggle navigation"
              >
                <Menu size={18} />
              </Button>
              <span className="breadcrumb-muted">Workspace</span>
              <span className="slash">/</span>
              <span>{current?.[0] || "Details"}</span>
            </div>
            <div className="topbar-right">
              <Link className="search-link" href="/runs">
                <Search size={15} />
                <span>Explore telemetry</span>
                <ArrowUpRight size={12} />
              </Link>
              <span className="top-divider" />
              <span className="live-indicator">
                <span
                  className={`status-dot ${connected ? "green pulse" : "amber"}`}
                />
                {connected ? "Live updates" : "Reconnecting"}
              </span>
            </div>
          </header>
          <main>
            {projectsQuery.isError ? (
              <div className="error-state">
                <AlertCircle size={28} />
                <h2>Unable to connect to the API</h2>
                <p>{projectsQuery.error.message}</p>
                <Button onClick={() => projectsQuery.refetch()}>
                  <RefreshCw size={15} />
                  Retry connection
                </Button>
              </div>
            ) : !project ? (
              <div className="loading-state">
                <Activity className="spin" size={24} />
                Connecting to your workspace…
              </div>
            ) : (
              children
            )}
          </main>
          <footer className="footer">
            <span>
              <span className="status-dot green" /> AgentScope · Observe.
              Understand. Recover.
            </span>
            <span>Local mode · Persistent telemetry</span>
          </footer>
        </div>
        {toast && (
          <div
            className={`toast ${toast.error ? "toast-error" : ""}`}
            role={toast.error ? "alert" : "status"}
          >
            {toast.error ? <AlertCircle size={18} /> : <Check size={18} />}
            <span>{toast.message}</span>
            <button
              onClick={() => setToast(null)}
              aria-label="Dismiss notification"
            >
              <X size={15} />
            </button>
          </div>
        )}
      </div>
    </Ctx.Provider>
  );
}
