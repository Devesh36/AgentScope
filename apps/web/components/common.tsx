"use client";
import Link from "next/link";
import {
  AlertCircle,
  ArrowRight,
  ChevronLeft,
  ChevronRight,
  Clock3,
  FlaskConical,
  Inbox,
  RefreshCw,
} from "lucide-react";
import type { UseQueryResult } from "@tanstack/react-query";
import { useWorkspace } from "./workspace";
import { Button } from "./ui/button";
import { label } from "@/lib/format";
export function PageHeader({
  title,
  description,
  actions,
  filters = false,
}: {
  title: string;
  description: string;
  actions?: React.ReactNode;
  filters?: boolean;
}) {
  const { project, setProject, projects, hours, setHours, source, setSource } =
    useWorkspace();
  return (
    <>
      <div className="page-header">
        <div>
          <div className="eyebrow page-eyebrow">AGENT OBSERVABILITY</div>
          <h1>{title}</h1>
          <p>{description}</p>
        </div>
        <div className="page-actions">{actions}</div>
      </div>
      <div className="page-toolbar">
        <div className="toolbar-group">
          <span className="toolbar-label">Project</span>
          <select
            aria-label="Project"
            value={project}
            onChange={(e) => setProject(e.target.value)}
          >
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
          {filters && (
            <select
              aria-label="Telemetry source"
              value={source}
              onChange={(e) => setSource(e.target.value)}
            >
              <option value="all">All telemetry</option>
              <option value="live">Live telemetry only</option>
              <option value="demo">Demo data only</option>
            </select>
          )}
        </div>
        {filters ? (
          <div className="time-filter">
            <Clock3 size={14} />
            <select
              aria-label="Time range"
              value={hours}
              onChange={(e) => setHours(Number(e.target.value))}
            >
              <option value={1}>Last hour</option>
              <option value={6}>Last 6 hours</option>
              <option value={24}>Last 24 hours</option>
              <option value={168}>Last 7 days</option>
            </select>
          </div>
        ) : (
          <span className="toolbar-caption">Project-scoped data</span>
        )}
      </div>
    </>
  );
}
export function Badge({
  value,
  demo = false,
}: {
  value: string;
  demo?: boolean;
}) {
  return (
    <span
      className={`badge ${demo ? "badge-demo" : `badge-${value.toLowerCase()}`}`}
    >
      {!demo && <span className="badge-dot" />}
      {demo ? "Demo data" : label(value)}
    </span>
  );
}
export function DemoNotice({ count }: { count?: number }) {
  return (
    <div className="demo-notice">
      <FlaskConical size={15} />
      <span>
        <strong>Synthetic telemetry</strong> ·{" "}
        {count ? `${count} demo runs in this view. ` : ""}Generated in the
        simulation lab and stored separately from live agent telemetry.
      </span>
      <Link href="/simulation">
        Simulation lab <ArrowRight size={13} />
      </Link>
    </div>
  );
}
export function Panel({
  title,
  subtitle,
  action,
  children,
  className = "",
}: {
  title: string;
  subtitle?: string;
  action?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={`panel ${className}`}>
      <div className="panel-header">
        <div>
          <h2>{title}</h2>
          {subtitle && <p>{subtitle}</p>}
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}
export function Empty({
  title = "No data yet",
  description,
  action,
  compact = false,
}: {
  title?: string;
  description: string;
  action?: React.ReactNode;
  compact?: boolean;
}) {
  return (
    <div className={`empty ${compact ? "empty-compact" : ""}`}>
      <div className="empty-icon">
        <Inbox size={22} />
      </div>
      <h3>{title}</h3>
      <p>{description}</p>
      {action}
    </div>
  );
}
export function DataState({
  query,
  children,
}: {
  query: Pick<UseQueryResult, "isPending" | "isError" | "error" | "refetch">;
  children: React.ReactNode;
}) {
  if (query.isPending)
    return (
      <div className="skeleton-grid">
        <div className="skeleton" />
        <div className="skeleton" />
        <div className="skeleton wide" />
      </div>
    );
  if (query.isError)
    return (
      <div className="error-state">
        <AlertCircle size={26} />
        <h3>Couldn’t load this view</h3>
        <p>
          {query.error instanceof Error
            ? query.error.message
            : "Please try again."}
        </p>
        <Button onClick={() => query.refetch()}>
          <RefreshCw size={14} />
          Retry
        </Button>
      </div>
    );
  return children;
}
export function Pagination({
  offset,
  total,
  size = 20,
  onChange,
}: {
  offset: number;
  total: number;
  size?: number;
  onChange: (v: number) => void;
}) {
  return (
    <nav className="pagination" aria-label="Results pagination">
      <span role="status" aria-live="polite">
        {total ? `${offset + 1}–${Math.min(offset + size, total)}` : "0"} of{" "}
        {total} results
      </span>
      <div>
        <Button
          aria-label="Previous page"
          disabled={offset === 0}
          onClick={() => onChange(Math.max(0, offset - size))}
        >
          <ChevronLeft size={15} />
        </Button>
        <Button
          aria-label="Next page"
          disabled={offset + size >= total}
          onClick={() => onChange(offset + size)}
        >
          <ChevronRight size={15} />
        </Button>
      </div>
    </nav>
  );
}
export function Field({
  label: text,
  children,
  hint,
}: {
  label: string;
  children: React.ReactNode;
  hint?: string;
}) {
  return (
    <label className="field">
      <span>{text}</span>
      {children}
      {hint && <small>{hint}</small>}
    </label>
  );
}
export function Json({ value }: { value: unknown }) {
  return <pre className="json">{JSON.stringify(value, null, 2)}</pre>;
}
export function Back({
  href,
  children,
}: {
  href: string;
  children: React.ReactNode;
}) {
  return (
    <Link href={href} className="back-link">
      <ChevronLeft size={14} />
      {children}
    </Link>
  );
}
