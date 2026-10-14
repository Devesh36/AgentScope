"use client";
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  ArrowUpRight,
  CheckCheck,
  ChevronRight,
  ClipboardCheck,
  Clock3,
  FileSearch,
  Fingerprint,
  FlaskConical,
  ListChecks,
  ShieldCheck,
  ShieldAlert,
  Sparkles,
  TriangleAlert,
} from "lucide-react";
import type {
  Incident,
  Investigation,
  Paginated,
  Remediation,
} from "@/lib/types";
import { date, label, number, relative } from "@/lib/format";
import { useAction, useData, useWorkspace } from "./workspace";
import {
  Back,
  Badge,
  DataState,
  DemoNotice,
  Empty,
  Json,
  PageHeader,
  Pagination,
  Panel,
} from "./common";
import { Button } from "./ui/button";
import { Dialog } from "./ui/dialog";
import { Row } from "./telemetry-pages";
import { ExplorerActions, ExplorerSearch, useExplorerFilters } from "./explorer-filters";
export function IncidentsPage() {
  const { search, status, severity, sort, offset, searchKey, update, reset, setOffset } = useExplorerFilters("incidents");
  const query = useData<Paginated<Incident>>(
    `incidents?limit=20&offset=${offset}&search=${encodeURIComponent(search)}&sort=${sort}${status !== "all" ? `&status=${status}` : ""}${severity !== "all" ? `&severity=${severity}` : ""}`,
  );
  const metrics = useData<{
    active_incidents: number;
    investigations: Investigation[];
  }>("metrics/overview");
  return (
    <>
      <PageHeader
        title="Incident center"
        description="Detect the unusual. Investigate with evidence. Recover with confidence."
        actions={
          <>
          <ExplorerActions kind="incidents" reset={reset} />
          <Button asChild>
            <Link href="/simulation">
              <FlaskConical size={15} />
              Trigger a demo incident
            </Link>
          </Button>
          </>
        }
      />
      <div className="incident-summary">
        <div>
          <span className="summary-icon amber">
            <ShieldAlert size={20} />
          </span>
          <div>
            <strong>{number(metrics.data?.active_incidents)}</strong>
            <span>Active incidents</span>
          </div>
        </div>
        <div>
          <span className="summary-icon purple">
            <FileSearch size={20} />
          </span>
          <div>
            <strong>
              {number(
                metrics.data?.investigations.filter((i) =>
                  ["queued", "running"].includes(i.status),
                ).length,
              )}
            </strong>
            <span>Recent investigations in progress</span>
          </div>
        </div>
        <div className="summary-note">
          <ShieldCheck size={18} />
          <span>
            Evidence-grounded investigation
            <br />
            <strong>Recommendation-only by default</strong>
          </span>
        </div>
      </div>
      <div className="filter-row">
        <ExplorerSearch key={searchKey} kind="incidents" value={search} onChange={(value) => update({ q: value }, true)} />
        <select
          aria-label="Incident status"
          value={status}
          onChange={(e) => update({ status: e.target.value })}
        >
          <option value="active">Active incidents</option>
          <option value="all">All statuses</option>
          {[
            "OPEN",
            "INVESTIGATING",
            "ACTION_REQUIRED",
            "VERIFYING",
            "RESOLVED",
            "DISMISSED",
          ].map((s) => (
            <option key={s} value={s}>
              {label(s)}
            </option>
          ))}
        </select>
        <select
          aria-label="Incident severity"
          value={severity}
          onChange={(e) => update({ severity: e.target.value })}
        >
          <option value="all">All severities</option>
          {["critical", "high", "medium", "low"].map((s) => (
            <option key={s}>{s}</option>
          ))}
        </select>
        <select
          aria-label="Sort incidents"
          value={sort}
          onChange={(e) => update({ sort: e.target.value })}
        >
          <option value="newest">Newest first</option>
          <option value="oldest">Oldest first</option>
        </select>
        <span className="muted small" role="status" aria-live="polite">{query.isPending ? "Loading incidents…" : `${number(query.data?.total)} incidents`}</span>
      </div>
      <DataState query={query}>
        <Panel
          title="Incidents"
          subtitle={`${query.data?.total || 0} results · Detected from recorded telemetry`}
        >
          {query.data?.items.length ? (
            <>
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Incident</th>
                      <th>Severity</th>
                      <th>Status</th>
                      <th>Affected agent</th>
                      <th>Investigation</th>
                      <th>Detected</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {query.data.items.map((i) => (
                      <tr key={i.id}>
                        <td>
                          <Link
                            className="table-main"
                            href={`/incidents/${i.id}`}
                          >
                            <span
                              className={`severity-bar severity-${i.severity}`}
                            />
                            <div>
                              <strong>{i.title}</strong>
                              <span className="mono">
                                INC-{i.id.slice(0, 6).toUpperCase()}
                                {i.synthetic && <Badge value="demo" demo />}
                              </span>
                            </div>
                          </Link>
                        </td>
                        <td>
                          <Badge value={i.severity} />
                        </td>
                        <td>
                          <Badge value={i.status} />
                        </td>
                        <td>
                          <Link href={`/agents/${i.agent_id}`}>
                            {i.agent_name.replace("demo/", "")}
                          </Link>
                        </td>
                        <td>
                          {i.investigation_id ? (
                            <Link
                              className="text-purple"
                              href={`/investigations/${i.investigation_id}`}
                            >
                              {label(i.investigation_status || "queued")}{" "}
                              <ArrowUpRight size={12} />
                            </Link>
                          ) : (
                            <span className="muted">Not started</span>
                          )}
                        </td>
                        <td className="muted nowrap">
                          {relative(i.created_at)}
                        </td>
                        <td>
                          <Link
                            aria-label={`View incident ${i.title}`}
                            href={`/incidents/${i.id}`}
                          >
                            <ChevronRight size={15} />
                          </Link>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <Pagination
                offset={offset}
                total={query.data.total}
                onChange={setOffset}
              />
            </>
          ) : (
            <Empty
              title="No incidents in this view"
              description="Adjust your filters or run a reproducible demo scenario to explore the incident response workflow."
              action={
                offset > 0 ? <Button onClick={() => setOffset(0)}>Return to first page</Button> : <Button onClick={reset}>Reset filters</Button>
              }
            />
          )}
        </Panel>
      </DataState>
    </>
  );
}
export function IncidentDetail({ id }: { id: string }) {
  const query = useData<Incident>(`incidents/${id}`);
  const i = query.data;
  const { act, pending } = useAction();
  const router = useRouter();
  async function start() {
    const inv = await act<Investigation>(
      `incidents/${id}/investigate`,
      {},
      "Investigation started",
    );
    if (inv) router.push(`/investigations/${inv.id}`);
  }
  return (
    <>
      <Back href="/incidents">Incident center</Back>
      <PageHeader
        title={i?.title || "Incident details"}
        description={`INC-${id.slice(0, 6).toUpperCase()} · Investigation, action history, and recovery verification.`}
        actions={
          i && (
            <>
              {i.investigation_id ? (
                <Button variant="primary" asChild>
                  <Link href={`/investigations/${i.investigation_id}`}>
                    <Sparkles size={15} />
                    Open investigation
                  </Link>
                </Button>
              ) : (
                <Button variant="primary" disabled={pending} onClick={start}>
                  <Sparkles size={15} />
                  {pending ? "Starting…" : "Investigate incident"}
                </Button>
              )}
            </>
          )
        }
      />
      <DataState query={query}>
        {i && (
          <>
            {i.synthetic && <DemoNotice />}
            <div className="incident-detail-banner">
              <ShieldAlert size={22} />
              <div className="grow">
                <strong>{i.title}</strong>
                <span>
                  {i.agent_name} · Detected {date(i.created_at)}
                </span>
              </div>
              <Badge value={i.severity} />
              <Badge value={i.status} />
            </div>
            <div className="two-col">
              <Panel
                title="Detection evidence"
                subtitle={`Rule ${i.anomaly.kind} · Version ${i.anomaly.rule_version}`}
              >
                <div className="key-values">
                  {Object.entries(i.anomaly.measurements).map(([k, v]) => (
                    <Row
                      key={k}
                      name={label(k)}
                      value={
                        Array.isArray(v)
                          ? v.join(", ")
                          : String(v ?? "Unavailable")
                      }
                    />
                  ))}
                </div>
                <div className="evidence-note">
                  <Fingerprint size={15} />
                  {i.anomaly.evidence_ids.length} supporting span references
                </div>
                <div className="panel-pad">
                  <Button asChild>
                    <Link href={`/runs/${i.run_id}`}>
                      <ListChecks size={14} />
                      Inspect execution trace
                    </Link>
                  </Button>
                </div>
              </Panel>
              <Panel title="Affected execution">
                <div className="key-values">
                  <Row
                    name="Agent"
                    value={
                      <Link href={`/agents/${i.agent_id}`}>{i.agent_name}</Link>
                    }
                  />
                  <Row
                    name="Run ID"
                    value={
                      <Link className="mono" href={`/runs/${i.run_id}`}>
                        {i.run_id.slice(0, 16)}…
                      </Link>
                    }
                  />
                  <Row
                    name="Run status"
                    value={<Badge value={i.run?.status || "unknown"} />}
                  />
                  <Row
                    name="Investigation"
                    value={
                      i.investigation_status ? (
                        <Badge value={i.investigation_status} />
                      ) : (
                        "Not started"
                      )
                    }
                  />
                  <Row
                    name="Control capability"
                    value={
                      i.synthetic
                        ? "Isolated demo adapter"
                        : "Recommendation only"
                    }
                  />
                </div>
              </Panel>
            </div>
            {i.investigation?.report.summary && (
              <Panel
                title="Investigation results"
                action={
                  <Link
                    href={`/investigations/${i.investigation.id}`}
                    className="text-link"
                  >
                    Full workspace <ArrowUpRight size={13} />
                  </Link>
                }
              >
                <div className="report-summary">
                  <Sparkles size={20} />
                  <div>
                    <h3>Evidence-grounded decision summary</h3>
                    <p>{i.investigation.report.decision_summary}</p>
                    <div className="recommendation">
                      <strong>Recommended action</strong>
                      <p>{i.investigation.report.recommendation}</p>
                    </div>
                  </div>
                </div>
              </Panel>
            )}
            {i.remediation && (
              <RemediationPanel incident={i} remediation={i.remediation} />
            )}
            <Panel
              title="Incident audit history"
              subtitle="Persisted detection, investigation, approval, execution, and verification events"
            >
              {i.audit?.length ? (
                <div className="audit-timeline">
                  {i.audit.map((a) => (
                    <div key={a.id}>
                      <span className="timeline-dot" />
                      <strong>{label(a.action.replaceAll(".", "_"))}</strong>
                      <span>{date(a.created_at)}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <Empty compact description="No audit events recorded." />
              )}
            </Panel>
          </>
        )}
      </DataState>
    </>
  );
}
export function InvestigationsPage() {
  const query = useData<Investigation[]>("investigations");
  return (
    <>
      <PageHeader
        title="Investigations"
        description="Turn execution evidence into explanations and actionable next steps."
      />
      <DataState query={query}>
        {query.data?.length ? (
          <div className="investigations-grid">
            {query.data.map((i) => (
              <Link
                className="panel investigation-card"
                key={i.id}
                href={`/investigations/${i.id}`}
              >
                <div className="investigation-card-top">
                  <span className="investigation-icon">
                    <Sparkles size={20} />
                  </span>
                  <Badge value={i.status} />
                </div>
                <h2>{i.incident_title}</h2>
                <p>
                  {i.agent_name?.replace("demo/", "")} ·{" "}
                  {relative(i.created_at)}
                </p>
                <div className="progress-bar">
                  <span style={{ width: `${i.progress}%` }} />
                </div>
                <div className="investigation-card-footer">
                  <span>{i.phase}</span>
                  <strong>
                    {i.progress}% <ArrowUpRight size={13} />
                  </strong>
                </div>
                {i.report.decision_summary && (
                  <div className="card-decision">
                    {i.report.decision_summary}
                  </div>
                )}
              </Link>
            ))}
          </div>
        ) : (
          <Empty
            title="Start with a signal. Follow the evidence."
            description="Open an incident and start an investigation. AgentScope collects telemetry, evaluates hypotheses, and recommends a next step."
            action={
              <Button variant="primary" asChild>
                <Link href="/incidents">
                  <ShieldAlert size={15} />
                  Go to incident center
                </Link>
              </Button>
            }
          />
        )}
      </DataState>
    </>
  );
}
const phases = [
  "Collect evidence",
  "Build execution timeline",
  "Validate hypotheses",
  "Propose remediation",
  "Complete",
];
export function InvestigationDetail({ id }: { id: string }) {
  const query = useData<Investigation & { incident: Incident }>(
    `investigations/${id}`,
  );
  const inv = query.data;
  const [tab, setTab] = useState("evidence");
  return (
    <>
      <Back href="/investigations">All investigations</Back>
      <PageHeader
        title="Investigation workspace"
        description={
          inv?.incident.title ||
          "Gathering evidence from the affected execution."
        }
        actions={
          inv && (
            <>
              <Badge value={inv.status} />
              <Button asChild>
                <Link href={`/incidents/${inv.incident_id}`}>
                  View incident <ArrowUpRight size={14} />
                </Link>
              </Button>
            </>
          )
        }
      />
      <DataState query={query}>
        {inv && (
          <>
            {inv.report.synthetic && <DemoNotice />}
            <div className="investigation-progress panel">
              <div className="investigation-progress-title">
                <span className="investigation-icon">
                  <Sparkles size={22} />
                </span>
                <div className="grow">
                  <h2>
                    {inv.status === "complete"
                      ? "Investigation complete"
                      : inv.phase}
                  </h2>
                  <p>
                    {inv.status === "complete"
                      ? "An evidence-based report is ready for your review."
                      : "Read-only investigation · persistent progress · bounded execution"}
                  </p>
                </div>
                <strong>{inv.progress}%</strong>
              </div>
              <div className="progress-bar">
                <span style={{ width: `${inv.progress}%` }} />
              </div>
              <ol className="investigation-steps">
                {phases.map((phase, index) => (
                  <li
                    key={phase}
                    className={inv.progress >= (index + 1) * 20 ? "done" : ""}
                  >
                    <span>
                      {inv.progress >= (index + 1) * 20 ? (
                        <CheckCheck size={13} />
                      ) : (
                        index + 1
                      )}
                    </span>
                    {phase}
                  </li>
                ))}
              </ol>
            </div>
            {inv.report.decision_summary && (
              <Panel
                title="Decision summary"
                subtitle="Conclusions grounded in recorded evidence · No hidden reasoning"
              >
                <div className="report-summary">
                  <ShieldCheck size={22} />
                  <div>
                    <h3>{inv.report.decision_summary}</h3>
                    <p>{inv.report.summary}</p>
                    <span className="badge badge-supported">
                      Supported by {inv.report.evidence?.length || 0} referenced
                      spans
                    </span>
                  </div>
                </div>
              </Panel>
            )}
            <div className="investigation-layout">
              <div>
                <div className="tabs">
                  {[
                    ["evidence", "Evidence collected"],
                    ["hypotheses", "Hypotheses"],
                    ["timeline", "Execution timeline"],
                  ].map(([key, title]) => (
                    <button
                      key={key}
                      className={tab === key ? "active" : ""}
                      onClick={() => setTab(key)}
                    >
                      {title}
                    </button>
                  ))}
                </div>
                {tab === "evidence" && (
                  <Panel
                    title="Recorded observations"
                    subtitle="Traceable references from the affected run"
                  >
                    {inv.report.evidence?.length ? (
                      inv.report.evidence.map((e, n) => (
                        <div className="evidence-card" key={e.id}>
                          <div className="evidence-card-top">
                            <span className="evidence-number">E{n + 1}</span>
                            <strong>{e.name}</strong>
                            <Badge value={e.status} />
                          </div>
                          <div className="evidence-fields">
                            <span>
                              Span <code>{e.span_id}</code>
                            </span>
                            <span>{date(e.at)}</span>
                            {e.tokens > 0 && (
                              <span>{number(e.tokens)} tokens</span>
                            )}
                          </div>
                          {e.error && (
                            <div className="evidence-error">{e.error}</div>
                          )}
                          {e.argument_fingerprint && (
                            <p className="fingerprint">
                              Argument fingerprint{" "}
                              <code>{e.argument_fingerprint}</code>
                            </p>
                          )}
                          {e.result_fingerprint && (
                            <p className="fingerprint">
                              Result fingerprint{" "}
                              <code>{e.result_fingerprint}</code>
                            </p>
                          )}
                          <Link
                            href={`/runs/${inv.incident.run_id}`}
                            className="text-link"
                          >
                            View source trace <ArrowUpRight size={12} />
                          </Link>
                        </div>
                      ))
                    ) : (
                      <Empty
                        compact
                        title="Collecting observations"
                        description="Telemetry references will appear as evidence collection completes."
                      />
                    )}
                  </Panel>
                )}
                {tab === "hypotheses" && (
                  <Panel
                    title="Explanations to evaluate"
                    subtitle="Epistemic status is qualitative; no invented confidence scores"
                  >
                    {inv.report.hypotheses?.map((h, n) => (
                      <div className="hypothesis-card" key={n}>
                        <div>
                          <span className="eyebrow">HYPOTHESIS {n + 1}</span>
                          <Badge value={h.epistemic_status} />
                        </div>
                        <h3>{h.explanation}</h3>
                        <div className="hypothesis-evidence">
                          <div>
                            <strong>
                              <CheckCheck size={13} />
                              Supporting evidence
                            </strong>
                            <p>
                              {h.supporting_evidence.length
                                ? h.supporting_evidence
                                    .map(
                                      (ref) =>
                                        `E${(inv.report.evidence?.findIndex((e) => e.id === ref) ?? -1) + 1}`,
                                    )
                                    .join(", ")
                                : "No supporting evidence recorded"}
                            </p>
                          </div>
                          <div>
                            <strong>
                              <TriangleAlert size={13} />
                              Contradictory evidence
                            </strong>
                            <p>
                              {h.contradictory_evidence.length
                                ? h.contradictory_evidence
                                    .map(
                                      (ref) =>
                                        `E${(inv.report.evidence?.findIndex((e) => e.id === ref) ?? -1) + 1}`,
                                    )
                                    .join(", ")
                                : "None identified in available telemetry"}
                            </p>
                          </div>
                        </div>
                        <strong className="small muted">
                          Validation steps
                        </strong>
                        <ul>
                          {h.validation_steps.map((s) => (
                            <li key={s}>{s}</li>
                          ))}
                        </ul>
                      </div>
                    ))}
                    {!inv.report.hypotheses?.length && (
                      <Empty
                        compact
                        description="Hypotheses are generated after evidence is collected."
                      />
                    )}
                  </Panel>
                )}
                {tab === "timeline" && (
                  <Panel
                    title="Execution timeline"
                    subtitle="Observed execution events and persisted investigation checkpoints"
                  >
                    <div className="audit-timeline">
                      {inv.report.execution_timeline?.map((e) => (
                        <div key={e.id}>
                          <span className="timeline-dot" />
                          <strong>{e.name}</strong>
                          <Badge value={e.status} />
                          <span>{date(e.at)}</span>
                        </div>
                      ))}
                      {inv.timeline.map((p, n) => (
                        <div key={n}>
                          <span className="timeline-dot purple" />
                          <strong>{p.phase}</strong>
                          <span>{date(p.at)}</span>
                        </div>
                      ))}
                    </div>
                  </Panel>
                )}
              </div>
              <div className="investigation-aside">
                <Panel title="Investigation context">
                  <div className="key-values">
                    <Row
                      name="Affected agent"
                      value={
                        <Link href={`/agents/${inv.incident.agent_id}`}>
                          {inv.incident.agent_name.replace("demo/", "")}
                        </Link>
                      }
                    />
                    <Row
                      name="Severity"
                      value={<Badge value={inv.incident.severity} />}
                    />
                    <Row
                      name="Incident state"
                      value={<Badge value={inv.incident.status} />}
                    />
                    <Row
                      name="Investigator"
                      value="LangGraph · Evidence-first"
                    />
                    <Row name="Safety mode" value="Read-only evidence tools" />
                  </div>
                </Panel>
                {inv.report.recommendation && (
                  <Panel
                    title="Recommended remediation"
                    action={<ClipboardCheck size={16} className="text-green" />}
                  >
                    <div className="panel-pad">
                      <p>{inv.report.recommendation}</p>
                      <div className="privacy-note">
                        <ShieldCheck size={14} />A recommendation does not
                        execute an action.
                      </div>
                    </div>
                  </Panel>
                )}
                {inv.report.limitations && (
                  <Panel title="Report limitations">
                    <ul className="limitations">
                      {[
                        ...inv.report.limitations,
                        ...(inv.report.provider_note
                          ? [inv.report.provider_note]
                          : []),
                      ].map((l) => (
                        <li key={l}>{l}</li>
                      ))}
                    </ul>
                  </Panel>
                )}
              </div>
            </div>
            {inv.incident.remediation && (
              <RemediationPanel
                incident={inv.incident}
                remediation={inv.incident.remediation}
              />
            )}
          </>
        )}
      </DataState>
    </>
  );
}
function RemediationPanel({
  incident,
  remediation,
}: {
  incident: Incident;
  remediation: Remediation;
}) {
  const { act, pending } = useAction();
  const [confirm, setConfirm] = useState<"approve" | "execute" | null>(null);
  const verification = remediation.verification;
  return (
    <Panel
      title="Approval & recovery"
      subtitle="Explicit approval, capability checks, audited execution, and independent verification"
      action={<Badge value={remediation.status} />}
    >
      <div className="remediation-content">
        <div className="grow">
          <h3>
            {incident.synthetic
              ? "Cancel the isolated demo run"
              : "Proposed intervention: cancel the affected run"}
          </h3>
          <p>
            {incident.synthetic
              ? "This action controls only the simulation adapter. Enable demo control in Settings before executing."
              : "This agent has no registered control adapter. The recommendation can be approved, but execution is unavailable."}
          </p>
          <div className="remediation-flags">
            <span>
              <ShieldCheck size={13} />
              Policy validated at execution
            </span>
            <span>
              <Fingerprint size={13} />
              Idempotent & audited
            </span>
          </div>
        </div>
        <div className="remediation-actions">
          {remediation.status === "proposed" && (
            <Button
              variant="primary"
              disabled={pending}
              onClick={() => setConfirm("approve")}
            >
              <CheckCheck size={15} />
              Approve proposal
            </Button>
          )}
          {remediation.status === "approved" && (
            <Button
              variant="primary"
              disabled={pending || !incident.synthetic}
              onClick={() => setConfirm("execute")}
            >
              <ClipboardCheck size={15} />
              Execute demo action
            </Button>
          )}
          {remediation.status === "verifying" && (
            <span className="verification-pending">
              <Clock3 size={15} />
              Observing recovery window…
            </span>
          )}
          {remediation.status === "executed" && (
            <Badge value={verification.result || "INCONCLUSIVE"} />
          )}
        </div>
      </div>
      {verification.result && (
        <div
          className={`verification-result ${verification.result === "VERIFIED_RECOVERED" ? "verified" : ""}`}
        >
          <ShieldCheck size={20} />
          <div className="grow">
            <h3>
              {verification.result === "PENDING"
                ? "Recovery verification in progress"
                : label(verification.result)}
            </h3>
            <p>
              {verification.result === "PENDING"
                ? `Observing a ${verification.window_seconds}-second window. Action success alone is insufficient.`
                : "Measurements collected after the approved intervention."}
            </p>
            {verification.measurements && (
              <div className="verification-measurements">
                {Object.entries(verification.measurements).map(([k, v]) => (
                  <span key={k}>
                    {label(k)} <strong>{String(v)}</strong>
                  </span>
                ))}
              </div>
            )}
            {verification.evidence_ids?.map((ref) => (
              <Link className="text-link" href={`/runs/${ref}`} key={ref}>
                Inspect follow-up run {ref.slice(0, 8)}{" "}
                <ArrowUpRight size={12} />
              </Link>
            ))}
          </div>
        </div>
      )}
      <Dialog
        open={!!confirm}
        onOpenChange={(v) => {
          if (!v) setConfirm(null);
        }}
        title={
          confirm === "approve"
            ? "Approve this remediation proposal?"
            : "Execute the demo intervention?"
        }
        description={
          confirm === "approve"
            ? "Approval records your decision. Execution remains a separate action, subject to policy and target capabilities."
            : "The isolated simulation run will be cancelled. Synthetic follow-up telemetry will verify recovery over a 15-second window."
        }
      >
        <div className="confirmation-body">
          <Row name="Affected agent" value={incident.agent_name} />
          <Row name="Action" value="Cancel run" />
          <Row
            name="Scope"
            value={
              incident.synthetic ? "Synthetic demo only" : "Recommendation only"
            }
          />
        </div>
        <div className="form-actions">
          <Button onClick={() => setConfirm(null)}>Cancel</Button>
          <Button
            variant="primary"
            disabled={pending}
            onClick={async () => {
              const result = await act<Remediation>(
                `remediations/${remediation.id}/${confirm}`,
                {},
                confirm === "approve"
                  ? "Proposal approved. Execution is a separate action."
                  : "Demo intervention executed. Verification is running.",
              );
              if (result) setConfirm(null);
            }}
          >
            {pending
              ? "Submitting…"
              : confirm === "approve"
                ? "Approve proposal"
                : "Execute demo action"}
          </Button>
        </div>
      </Dialog>
    </Panel>
  );
}
