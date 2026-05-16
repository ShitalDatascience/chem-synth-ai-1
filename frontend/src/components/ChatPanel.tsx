"use client";

import { useCallback, useEffect, useId, useRef, useState } from "react";

import type {
  ChatResponse,
  FinalReport,
  TargetReportResponse,
  ToxicityRiskResponse,
} from "@/types/chat";
import { ValidationWarning } from "@/components/ValidationWarning";

type ChatMessage =
  | { id: string; role: "user"; text: string }
  | { id: string; role: "assistant"; response: ChatResponse }
  | { id: string; role: "assistant"; error: string };

const REPORT_SECTION_KEYS = [
  "executive_summary",
  "molecular_identity",
  "physchem",
  "similar_compounds",
  "chembl_evidence",
  "predictions",
  "risks",
  "next_experiments",
  "citations",
  "disclaimer",
] as const;

const SECTION_LABELS: Record<string, string> = {
  executive_summary: "Executive summary",
  molecular_identity: "Molecular identity",
  physchem: "Physicochemical",
  similar_compounds: "Similar compounds (narrative)",
  chembl_evidence: "ChEMBL evidence",
  predictions: "Model predictions (narrative)",
  risks: "Risks",
  next_experiments: "Next experiments",
  citations: "Citations",
  disclaimer: "Disclaimer",
};

function sectionHeading(key: string): string {
  return SECTION_LABELS[key] ?? key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatNum(n: unknown): string {
  if (typeof n !== "number" || Number.isNaN(n)) return "—";
  if (Math.abs(n) >= 1000) return n.toLocaleString(undefined, { maximumFractionDigits: 3 });
  return String(n);
}

function moleculePropertyRows(mol: Record<string, unknown>): [string, string][] {
  const rows: [string, string][] = [];
  if (mol.mw != null) rows.push(["Molecular weight", `${formatNum(mol.mw)} g/mol`]);
  if (mol.formula != null) rows.push(["Formula", String(mol.formula)]);
  if (mol.logp != null) rows.push(["LogP", String(mol.logp)]);
  if (mol.hbd != null && mol.hba != null) rows.push(["HBD / HBA", `${mol.hbd} / ${mol.hba}`]);
  if (mol.tpsa != null) rows.push(["TPSA", `${formatNum(mol.tpsa)} Å²`]);
  if (mol.rot_bonds != null) rows.push(["Rotatable bonds", String(mol.rot_bonds)]);
  return rows;
}

function resolveReportTitle(report: FinalReport): string {
  const mol = report.molecule ?? {};
  const pref = typeof mol.pref_name === "string" && mol.pref_name.trim() ? mol.pref_name.trim() : null;
  if (pref) return pref;

  const mid = report.report_sections?.molecular_identity?.trim();
  if (mid) return mid;

  const q = report.query?.trim();
  if (q) return q;

  const chembl = typeof mol.chembl_id === "string" ? mol.chembl_id : null;
  return chembl ? `Molecule ${chembl}` : "Assistant response";
}

/** Skip narrative `similar_compounds` when empty and we render the data table instead. */
function shouldRenderSectionText(key: string, text: string, hasSimilarRows: boolean): boolean {
  const t = text.trim();
  if (!t) return false;
  if (key === "similar_compounds" && hasSimilarRows) return false;
  return true;
}

function dedupeSectionBlocks(
  sections: Record<string, string>,
  opts: { skipKeys: Set<string> },
): { key: string; text: string }[] {
  const seen = new Set<string>();
  const out: { key: string; text: string }[] = [];

  for (const key of REPORT_SECTION_KEYS) {
    if (opts.skipKeys.has(key)) continue;
    const text = (sections[key] ?? "").trim();
    if (!text) continue;
    const norm = text.replace(/\s+/g, " ");
    if (seen.has(norm)) continue;
    seen.add(norm);
    out.push({ key, text: sections[key] ?? "" });
  }
  return out;
}

async function postChat(query: string): Promise<ChatResponse> {
  // Use the Next.js proxy route (/api/chat) to avoid browser CORS restrictions.
  const res = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query }),
  });

  const text = await res.text();
  if (!res.ok) {
    let detail = res.statusText || `HTTP ${res.status}`;
    try {
      const errJson = JSON.parse(text) as { detail?: unknown };
      if (typeof errJson.detail === "string") detail = errJson.detail;
      else if (Array.isArray(errJson.detail))
        detail = errJson.detail.map((d) => JSON.stringify(d)).join("; ");
    } catch {
      if (text) detail = text.slice(0, 500);
    }
    throw new Error(detail);
  }

  return JSON.parse(text) as ChatResponse;
}

function Panel({
  title,
  subtitle,
  children,
  className = "",
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={`border border-outline-variant bg-surface-container-lowest rounded-DEFAULT overflow-hidden ${className}`}>
      <div className="bg-surface-container-low px-3 py-2 border-b border-outline-variant flex flex-col gap-0.5 sm:flex-row sm:items-center sm:justify-between">
        <h4 className="font-label-caps text-label-caps text-on-surface uppercase">{title}</h4>
        {subtitle ? (
          <span className="font-data-mono text-data-mono text-on-surface-variant text-[11px]">{subtitle}</span>
        ) : null}
      </div>
      <div className="p-4">{children}</div>
    </div>
  );
}

function SimilarCompoundsFromReport({ rows }: { rows: Record<string, unknown>[] }) {
  if (!rows.length) return null;
  return (
    <Panel title="Similar compounds" subtitle={`${rows.length} match${rows.length === 1 ? "" : "es"}`}>
      <div className="overflow-x-auto -m-4">
        <table className="w-full text-left border-collapse min-w-[520px]">
          <thead>
            <tr className="border-b border-outline-variant bg-surface-container-low font-label-caps text-label-caps text-on-surface-variant uppercase text-[10px]">
              <th className="p-3 w-14"> </th>
              <th className="p-3">ChEMBL ID</th>
              <th className="p-3">Tanimoto</th>
              <th className="p-3">SMILES</th>
              <th className="p-3">Headline activity</th>
            </tr>
          </thead>
          <tbody className="font-data-mono text-data-mono text-on-surface text-body-md">
            {rows.map((r, i) => {
              const id = String(r.chembl_id ?? "—");
              const tan = typeof r.tanimoto === "number" ? r.tanimoto : null;
              const smiles = typeof r.canonical_smiles === "string" ? r.canonical_smiles : "—";
              const head =
                typeof r.headline_activity === "string" && r.headline_activity
                  ? r.headline_activity
                  : "—";
              const pct = tan != null ? Math.round(tan * 100) : 0;
              return (
                <tr
                  key={`${id}-${i}`}
                  className={i % 2 === 1 ? "bg-surface-container-low/60 border-b border-outline-variant/40" : "border-b border-outline-variant/40"}
                >
                  <td className="p-3 w-14">
                    <div className="w-10 h-10 bg-surface-container-high border border-outline-variant/50 rounded flex items-center justify-center">
                      <span className="material-symbols-outlined text-[18px] text-on-surface-variant">category</span>
                    </div>
                  </td>
                  <td className="p-3 font-medium whitespace-nowrap">{id}</td>
                  <td className="p-3 whitespace-nowrap">
                    {tan != null ? (
                      <div className="flex items-center gap-2">
                        <div className="w-20 h-1.5 bg-surface-container-high rounded-full overflow-hidden border border-outline-variant/30">
                          <div className="h-full bg-primary" style={{ width: `${pct}%` }} />
                        </div>
                        <span>{tan.toFixed(3)}</span>
                      </div>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td className="p-3 max-w-[240px]">
                    <code className="text-[11px] leading-snug break-all text-on-surface">{smiles}</code>
                  </td>
                  <td className="p-3 text-body-md max-w-[180px]">{head}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

function EvidenceFromReport({ ev }: { ev: Record<string, unknown> }) {
  const summary = typeof ev.summary_text === "string" ? ev.summary_text.trim() : "";
  const topTargets = Array.isArray(ev.top_targets) ? ev.top_targets : [];
  const potency = Array.isArray(ev.potency_stats_by_target) ? ev.potency_stats_by_target : [];
  const assayCounts = ev.assay_counts && typeof ev.assay_counts === "object" ? (ev.assay_counts as Record<string, number>) : null;
  const total = ev.total_activities;
  const clusters = Array.isArray(ev.target_clusters) ? ev.target_clusters : [];

  if (!summary && !topTargets.length && !potency.length && !assayCounts && clusters.length === 0) return null;

  return (
    <div className="space-y-4">
      {summary ? (
        <Panel title="Evidence summary" subtitle={typeof total === "number" ? `${formatNum(total)} activities` : undefined}>
          <p className="font-body-md text-body-md text-on-surface leading-relaxed">{summary}</p>
        </Panel>
      ) : null}

      {topTargets.length > 0 ? (
        <Panel title="Top targets" subtitle="By activity count">
          <div className="overflow-x-auto -m-4">
            <table className="w-full text-left border-collapse min-w-[360px]">
              <thead>
                <tr className="border-b border-outline-variant font-label-caps text-label-caps text-on-surface-variant uppercase text-[10px]">
                  <th className="p-2 pl-4">Target</th>
                  <th className="p-2 pr-4 text-right">Count</th>
                </tr>
              </thead>
              <tbody className="font-body-md text-on-surface">
                {topTargets.slice(0, 12).map((row, i) => {
                  const o = row as Record<string, unknown>;
                  const name = typeof o.target === "string" ? o.target : "—";
                  const count = typeof o.count === "number" ? o.count : "—";
                  return (
                    <tr key={`${name}-${i}`} className="border-b border-outline-variant/30">
                      <td className="p-2 pl-4">{name}</td>
                      <td className="p-2 pr-4 text-right font-data-mono text-data-mono">{count}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Panel>
      ) : null}

      {potency.length > 0 ? (
        <Panel title="Potency by target" subtitle="IC50 and related">
          <div className="overflow-x-auto -m-4">
            <table className="w-full text-left border-collapse min-w-[560px]">
              <thead>
                <tr className="border-b border-outline-variant font-label-caps text-label-caps text-on-surface-variant uppercase text-[10px]">
                  <th className="p-2 pl-4">Target</th>
                  <th className="p-2">Type</th>
                  <th className="p-2 text-right">Median</th>
                  <th className="p-2 text-right">Min–max</th>
                  <th className="p-2 pr-4 text-right">n</th>
                </tr>
              </thead>
              <tbody className="font-data-mono text-data-mono text-on-surface text-[12px]">
                {potency.map((row, i) => {
                  const o = row as Record<string, unknown>;
                  const target = String(o.target ?? "—");
                  const atype = String(o.activity_type ?? "—");
                  const unit = String(o.unit ?? "");
                  const med = o.median_value;
                  const minv = o.min_value;
                  const maxv = o.max_value;
                  const n = o.sample_size;
                  const range =
                    typeof minv === "number" && typeof maxv === "number"
                      ? `${formatNum(minv)}–${formatNum(maxv)}`
                      : "—";
                  return (
                    <tr key={`${target}-${i}`} className="border-b border-outline-variant/30">
                      <td className="p-2 pl-4 align-top">{target}</td>
                      <td className="p-2 align-top">{atype}</td>
                      <td className="p-2 text-right align-top whitespace-nowrap">
                        {typeof med === "number" ? `${formatNum(med)} ${unit}`.trim() : "—"}
                      </td>
                      <td className="p-2 text-right align-top whitespace-nowrap">{range}</td>
                      <td className="p-2 pr-4 text-right align-top">{n != null ? String(n) : "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Panel>
      ) : null}

      {assayCounts && Object.keys(assayCounts).length > 0 ? (
        <Panel title="Assay class counts" subtitle="ChEMBL assay types">
          <div className="flex flex-wrap gap-2">
            {Object.entries(assayCounts).map(([k, v]) => (
              <span
                key={k}
                className="inline-flex items-baseline gap-1.5 rounded-sm border border-outline-variant/60 bg-surface px-2 py-1 font-data-mono text-[12px]"
              >
                <span className="text-on-surface-variant font-label-caps text-[10px]">{k}</span>
                <span className="text-on-surface">{formatNum(v)}</span>
              </span>
            ))}
          </div>
        </Panel>
      ) : null}

      {clusters.length > 0 ? (
        <Panel title="Target clusters" subtitle="Activity groupings">
          <div className="space-y-4">
            {clusters.map((c, ci) => {
              const o = c as Record<string, unknown>;
              const label = typeof o.cluster === "string" ? o.cluster : `Cluster ${ci + 1}`;
              const tot = o.total_activities;
              const tops = Array.isArray(o.top_targets) ? o.top_targets : [];
              return (
                <div key={`${label}-${ci}`} className="border border-outline-variant/50 rounded-sm overflow-hidden">
                  <div className="bg-surface-container-low px-3 py-1.5 flex justify-between items-center gap-2">
                    <span className="font-label-caps text-label-caps text-on-surface uppercase text-[10px]">
                      {label}
                    </span>
                    {typeof tot === "number" ? (
                      <span className="font-data-mono text-[11px] text-on-surface-variant">
                        {formatNum(tot)} activities
                      </span>
                    ) : null}
                  </div>
                  <ul className="p-3 space-y-1 font-body-md text-body-md text-on-surface">
                    {tops.slice(0, 8).map((t, ti) => {
                      const to = t as Record<string, unknown>;
                      const tn = String(to.target ?? "—");
                      const tc = to.count;
                      return (
                        <li key={`${tn}-${ti}`} className="flex justify-between gap-2 border-b border-outline-variant/20 last:border-0 pb-1 last:pb-0">
                          <span>{tn}</span>
                          <span className="font-data-mono text-data-mono shrink-0">{tc != null ? String(tc) : "—"}</span>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              );
            })}
          </div>
        </Panel>
      ) : null}
    </div>
  );
}

function ExperimentsFromReport({ rows }: { rows: Record<string, unknown>[] }) {
  if (!rows.length) return null;
  return (
    <Panel title="Recommended experiments" subtitle="From pipeline">
      <div className="overflow-x-auto -m-4">
        <table className="w-full text-left border-collapse min-w-[480px]">
          <thead>
            <tr className="border-b border-outline-variant font-label-caps text-label-caps text-on-surface-variant uppercase text-[10px]">
              <th className="p-2 pl-4 w-24">Priority</th>
              <th className="p-2">Target</th>
              <th className="p-2 pr-4">Recommended assay</th>
            </tr>
          </thead>
          <tbody className="font-body-md text-body-md text-on-surface">
            {rows.map((r, i) => {
              const o = r as Record<string, unknown>;
              const pri = String(o.priority ?? "—");
              const tgt = String(o.target ?? "—");
              const assay = String(o.recommended_assay ?? o.assay_chembl_id ?? "—");
              const priClass =
                pri.toLowerCase() === "high"
                  ? "bg-error-container text-on-error-container"
                  : pri.toLowerCase() === "medium"
                    ? "bg-secondary-fixed-dim text-on-secondary-fixed"
                    : "bg-surface-container-high text-on-surface-variant";
              return (
                <tr key={`${tgt}-${i}`} className="border-b border-outline-variant/30 align-top">
                  <td className="p-2 pl-4">
                    <span className={`inline-block px-2 py-0.5 rounded-sm font-label-caps text-[9px] uppercase ${priClass}`}>
                      {pri}
                    </span>
                  </td>
                  <td className="p-2 font-medium">{tgt}</td>
                  <td className="p-2 pr-4 leading-snug text-on-surface-variant">{assay}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

function PredictionsFromReport({ preds }: { preds: Record<string, unknown>[] }) {
  if (!preds.length) return null;
  return (
    <Panel title="Model predictions" subtitle="DeepChem / in-silico">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {preds.map((p, i) => {
          const o = p as Record<string, unknown>;
          const task = String(o.task ?? "task");
          const value = o.value;
          const unit = o.unit != null ? String(o.unit) : "";
          const model = String(o.model_name ?? "");
          const ds = String(o.training_dataset ?? "");
          const label = String(o.label ?? "");
          const valueStr =
            typeof value === "number"
              ? `${value.toLocaleString(undefined, { maximumFractionDigits: 4 })}${unit ? ` ${unit}` : ""}`
              : value != null
                ? String(value)
                : "—";
          return (
            <div
              key={`${task}-${i}`}
              className="rounded-DEFAULT border border-outline-variant/60 bg-surface p-3 flex flex-col gap-1"
            >
              <div className="flex justify-between items-start gap-2">
                <span className="font-label-caps text-label-caps text-on-surface-variant uppercase text-[10px]">
                  {task}
                </span>
                {label ? (
                  <span className="text-[10px] font-data-mono text-on-surface-variant">{label}</span>
                ) : null}
              </div>
              <p className="font-data-mono text-data-mono text-lg text-on-surface">{valueStr}</p>
              <p className="font-body-md text-[11px] text-on-surface-variant leading-snug">
                {model}
                {ds ? ` · ${ds}` : ""}
              </p>
            </div>
          );
        })}
      </div>
    </Panel>
  );
}

function ReportSectionProse({ sectionKey, text }: { sectionKey: string; text: string }) {
  const body = text.trim();
  if (!body) return null;
  const isDisclaimer = sectionKey === "disclaimer";
  const isNextExp = sectionKey === "next_experiments";

  return (
    <section className={isDisclaimer ? "opacity-80" : ""}>
      <h3 className="font-label-caps text-label-caps text-on-surface-variant uppercase tracking-widest mb-2 border-b border-outline-variant/40 pb-1">
        {sectionHeading(sectionKey)}
      </h3>
      <div
        className={`font-body-md text-body-md text-on-surface leading-relaxed ${
          isNextExp ? "whitespace-pre-wrap pl-1" : "whitespace-pre-wrap"
        } ${isDisclaimer ? "text-on-surface-variant text-[12px]" : ""}`}
      >
        {isNextExp ? (
          <ul className="list-none space-y-2">
            {body.split(/\n+/).map((line, i) => {
              const trimmed = line.trim();
              if (!trimmed) return null;
              const content = trimmed.replace(/^•\s*/, "");
              const isBullet = trimmed.startsWith("•") || trimmed.startsWith("-");
              return (
                <li key={i} className={isBullet ? "flex gap-2" : ""}>
                  {isBullet ? <span className="text-primary shrink-0">•</span> : null}
                  <span>{content}</span>
                </li>
              );
            })}
          </ul>
        ) : (
          body
        )}
      </div>
    </section>
  );
}

function AssistantReport({ report }: { report: FinalReport }) {
  const mol = report.molecule ?? {};
  const chembl = typeof mol.chembl_id === "string" ? mol.chembl_id : null;
  const title = resolveReportTitle(report);
  const smiles = typeof mol.canonical_smiles === "string" ? mol.canonical_smiles : null;
  const propRows = moleculePropertyRows(mol);
  const similarRows = report.similar_compounds ?? [];
  const hasSimilarRows = similarRows.length > 0;
  const predRows = report.predictions ?? [];
  const hasPredRows = predRows.length > 0;
  const hasMwLogp = propRows.some(([l]) => l === "Molecular weight") && propRows.some(([l]) => l === "LogP");

  const sections = report.report_sections ?? {};
  const executive = (sections.executive_summary ?? "").trim();

  const skipProse = new Set<string>(["executive_summary"]);
  if (hasSimilarRows) skipProse.add("similar_compounds");
  if (hasPredRows) skipProse.add("predictions");
  if (hasMwLogp && (sections.physchem ?? "").trim()) skipProse.add("physchem");

  const sectionBlocks = dedupeSectionBlocks(sections, { skipKeys: skipProse }).filter(({ key, text }) =>
    shouldRenderSectionText(key, text, hasSimilarRows),
  );

  const disclaimer = (sections.disclaimer ?? "").trim();
  const showDisclaimer = disclaimer && !sectionBlocks.some((b) => b.key === "disclaimer");

  const meta = report.metadata;
  const metaLine =
    meta?.pipeline || meta?.model_version
      ? [meta.pipeline, meta.model_version].filter(Boolean).join(" · ")
      : null;

  return (
    <div className="bg-white p-6 rounded-lg border border-outline-variant shadow-sm w-full max-w-4xl space-y-6">
      <div className="flex flex-wrap items-center gap-2 border-b border-outline-variant/50 pb-3">
        <span className="font-headline-md text-headline-md text-primary">{title}</span>
        <span className="bg-tertiary-fixed-dim text-on-tertiary-fixed px-2 py-0.5 rounded-sm font-label-caps uppercase text-[10px]">
          Validated
        </span>
        {chembl ? (
          <span className="ml-auto font-data-mono text-data-mono text-on-surface-variant">ChEMBL ID: {chembl}</span>
        ) : null}
      </div>

      {executive ? (
        <div className="rounded-DEFAULT border border-primary/20 bg-surface-container-low p-4">
          <h3 className="font-label-caps text-label-caps text-primary uppercase tracking-widest mb-2">
            Executive summary
          </h3>
          <p className="font-body-md text-body-md text-on-surface leading-relaxed whitespace-pre-wrap">{executive}</p>
        </div>
      ) : null}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {propRows.length > 0 ? (
          <div className="lg:col-span-1 border border-outline-variant bg-surface-container-lowest rounded-DEFAULT overflow-hidden">
            <div className="bg-surface-container-low px-3 py-2 border-b border-outline-variant">
              <h4 className="font-label-caps text-label-caps text-on-surface uppercase">Physicochemical</h4>
            </div>
            <div className="p-4 space-y-3">
              {propRows.map(([label, value], i) => (
                <div
                  key={label}
                  className={`flex justify-between gap-2 pb-1 ${i < propRows.length - 1 ? "border-b border-outline-variant/30" : ""}`}
                >
                  <span className="font-body-md text-sm text-on-surface-variant">{label}</span>
                  <span className="font-data-mono text-data-mono text-right">{value}</span>
                </div>
              ))}
            </div>
          </div>
        ) : null}

        {smiles ? (
          <div
            className={`border border-outline-variant bg-surface-container-lowest rounded-DEFAULT overflow-hidden ${
              propRows.length ? "lg:col-span-2" : "lg:col-span-3"
            }`}
          >
            <div className="bg-surface-container-low px-3 py-2 border-b border-outline-variant">
              <h4 className="font-label-caps text-label-caps text-on-surface uppercase">SMILES</h4>
            </div>
            <div className="p-4">
              <code className="font-data-mono text-data-mono text-on-surface text-[12px] leading-relaxed break-all">
                {smiles}
              </code>
            </div>
          </div>
        ) : null}
      </div>

      <EvidenceFromReport ev={report.evidence_summary ?? {}} />

      <SimilarCompoundsFromReport rows={similarRows} />

      <ExperimentsFromReport rows={report.experiment_list ?? []} />

      <PredictionsFromReport preds={predRows} />

      {sectionBlocks.length > 0 ? (
        <div className="space-y-5 border-t border-outline-variant/40 pt-5">
          {sectionBlocks.map(({ key, text }) => (
            <ReportSectionProse key={key} sectionKey={key} text={text} />
          ))}
        </div>
      ) : null}

      {showDisclaimer ? (
        <ReportSectionProse sectionKey="disclaimer" text={disclaimer} />
      ) : null}

      {metaLine ? (
        <p className="font-data-mono text-[11px] text-on-surface-variant border-t border-outline-variant/40 pt-3">
          {metaLine}
        </p>
      ) : null}
    </div>
  );
}

function AssistantToxicityRisk({ response }: { response: ToxicityRiskResponse }) {
  const chips: string[] = [];
  const f = response.filters;
  if (Array.isArray(f.endpoints)) chips.push(`endpoints: ${(f.endpoints as string[]).join(", ")}`);
  if (Array.isArray(f.assay_types_allowed))
    chips.push(`assays: ${(f.assay_types_allowed as string[]).join(", ")}`);
  if (Array.isArray(f.standard_units_allowed))
    chips.push(`units: ${(f.standard_units_allowed as string[]).join(", ")}`);

  const tier = response.risk_summary;
  const tierCls =
    tier === "HIGH"
      ? "bg-red-600 text-white"
      : tier === "MEDIUM"
        ? "bg-amber-500 text-black"
        : tier === "LOW"
          ? "bg-emerald-700 text-white"
          : "bg-outline-variant text-on-surface-variant";

  return (
    <div className="bg-white p-6 rounded-lg border border-outline-variant shadow-sm w-full max-w-4xl space-y-4">
      <div className="flex flex-wrap items-center gap-2 border-b border-outline-variant/50 pb-3">
        <span className="font-headline-md text-headline-md text-primary">{response.target}</span>
        <span className="bg-secondary-fixed-dim text-on-secondary-fixed px-2 py-0.5 rounded-sm font-label-caps uppercase text-[10px]">
          Cardiac safety
        </span>
        <span className={`ml-auto px-3 py-0.5 rounded-full font-label-caps uppercase text-[11px] ${tierCls}`}>
          Risk signal: {tier}
        </span>
      </div>

      <p className="font-body-md text-body-md text-on-surface-variant leading-relaxed">{response.note}</p>

      {chips.length > 0 ? (
        <div className="flex flex-wrap gap-2">
          {chips.map((c) => (
            <span
              key={c}
              className="font-data-mono text-[11px] bg-surface-container-low border border-outline-variant/60 px-2 py-0.5 rounded-sm text-on-surface-variant"
            >
              {c}
            </span>
          ))}
        </div>
      ) : null}

      <Panel
        title="Experimental evidence (ChEMBL)"
        subtitle={`${response.experimental_evidence.length} molecule${response.experimental_evidence.length === 1 ? "" : "s"} (best row per compound)`}
      >
        <div className="overflow-x-auto -m-4">
          <table className="w-full text-left border-collapse min-w-[480px]">
            <thead>
              <tr className="border-b border-outline-variant font-label-caps text-label-caps text-on-surface-variant uppercase text-[10px]">
                <th className="p-2 pl-4">Compound</th>
                <th className="p-2">ChEMBL ID</th>
                <th className="p-2 pr-4">Potency / endpoint</th>
              </tr>
            </thead>
            <tbody className="font-data-mono text-data-mono text-on-surface text-[12px]">
              {response.experimental_evidence.length === 0 ? (
                <tr className="border-b border-outline-variant/30">
                  <td colSpan={3} className="p-4 text-on-surface-variant font-body-md text-body-md">
                    No qualifying rows returned from ChEMBL for these filters (try widening endpoints or organism).
                  </td>
                </tr>
              ) : (
                response.experimental_evidence.map((row, i) => (
                  <tr key={`${row.chembl_id}-${i}`} className="border-b border-outline-variant/30">
                    <td className="p-2 pl-4 font-body-md text-body-md">{String(row.compound ?? "—")}</td>
                    <td className="p-2">{String(row.chembl_id ?? "")}</td>
                    <td className="p-2 pr-4 whitespace-pre-wrap">{String(row.IC50 ?? "")}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Panel>

      <Panel title="Predicted overlay (models)" subtitle="Integrated ML tiers appear here when wired">
        {response.predicted_evidence.length === 0 ? (
          <p className="font-body-md text-body-md text-on-surface-variant px-4 pb-4">
            No surrogate model predictions supplied for this deployment. DeepChem / hERG QSAR stubs can be connected
            without changing this contract.
          </p>
        ) : (
          <div className="overflow-x-auto -m-4 px-4 pb-4">
            <table className="w-full text-left border-collapse min-w-[400px]">
              <thead>
                <tr className="border-b border-outline-variant font-label-caps text-[10px] uppercase text-on-surface-variant">
                  <th className="p-2">Compound</th>
                  <th className="p-2">risk_score</th>
                  <th className="p-2 pr-4">model</th>
                </tr>
              </thead>
              <tbody className="font-data-mono text-[12px]">
                {response.predicted_evidence.map((row, i) => (
                  <tr key={`${row.compound}-${i}`}>
                    <td className="p-2">{row.compound}</td>
                    <td className="p-2">{String(row.risk_score)}</td>
                    <td className="p-2 pr-4">{row.model}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <p className="font-data-mono text-[11px] text-on-surface-variant border-t border-outline-variant/40 pt-3">
        intent: {response.intent} · Experimental and predicted endpoints are split by design.
      </p>
    </div>
  );
}

function AssistantTargetReport({ response }: { response: TargetReportResponse }) {
  const { target_name, total, compounds, filters, intent, scaffold_clusters, physchem_trends } = response;
  const isSAR = intent === "sar_analysis";
  const filterChips: string[] = [];
  if (Array.isArray(filters.endpoints)) filterChips.push(`endpoints: ${(filters.endpoints as string[]).join(", ")}`);
  if (typeof filters.value_max_nm === "number") filterChips.push(`≤ ${filters.value_max_nm} nM`);
  if (typeof filters.value_min_nm === "number") filterChips.push(`≥ ${filters.value_min_nm} nM`);
  if (typeof filters.organism === "string" && filters.organism) filterChips.push(filters.organism);
  if (filters.exclude_cell_based === true) filterChips.push("binding-only");

  return (
    <div className="bg-white p-6 rounded-lg border border-outline-variant shadow-sm w-full max-w-4xl space-y-4">
      <div className="flex flex-wrap items-center gap-2 border-b border-outline-variant/50 pb-3">
        <span className="font-headline-md text-headline-md text-primary">{target_name}</span>
        <span className="bg-tertiary-fixed-dim text-on-tertiary-fixed px-2 py-0.5 rounded-sm font-label-caps uppercase text-[10px]">
          {isSAR ? "SAR analysis" : "Target lookup"}
        </span>
        <span className="ml-auto font-data-mono text-data-mono text-on-surface-variant">
          {total} compound{total === 1 ? "" : "s"}
        </span>
      </div>

      {filterChips.length > 0 ? (
        <div className="flex flex-wrap gap-2">
          {filterChips.map((c) => (
            <span
              key={c}
              className="font-data-mono text-[11px] bg-surface-container-low border border-outline-variant/60 px-2 py-0.5 rounded-sm text-on-surface-variant"
            >
              {c}
            </span>
          ))}
        </div>
      ) : null}

      {isSAR && physchem_trends.length > 0 ? (
        <Panel title="Physicochemical trends" subtitle={`Across ${total} ligands`}>
          <div className="overflow-x-auto -m-4">
            <table className="w-full text-left border-collapse min-w-[480px]">
              <thead>
                <tr className="border-b border-outline-variant font-label-caps text-label-caps text-on-surface-variant uppercase text-[10px]">
                  <th className="p-2 pl-4">Descriptor</th>
                  <th className="p-2 text-right">n</th>
                  <th className="p-2 text-right">Mean</th>
                  <th className="p-2 text-right">Median</th>
                  <th className="p-2 pr-4 text-right">Range</th>
                </tr>
              </thead>
              <tbody className="font-data-mono text-data-mono text-on-surface text-[12px]">
                {physchem_trends.map((t) => (
                  <tr key={t.descriptor} className="border-b border-outline-variant/30">
                    <td className="p-2 pl-4 font-body-md text-body-md">{t.label}</td>
                    <td className="p-2 text-right">{t.n}</td>
                    <td className="p-2 text-right whitespace-nowrap">
                      {formatNum(t.mean)} {t.unit}
                    </td>
                    <td className="p-2 text-right whitespace-nowrap">
                      {formatNum(t.median)} {t.unit}
                    </td>
                    <td className="p-2 pr-4 text-right whitespace-nowrap">
                      {formatNum(t.min)}–{formatNum(t.max)} {t.unit}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      ) : null}

      {isSAR && scaffold_clusters.length > 0 ? (
        <Panel title="Scaffold clusters" subtitle="Bemis–Murcko">
          <div className="space-y-2">
            {scaffold_clusters.map((c, i) => (
              <div
                key={`${c.scaffold || "acyclic"}-${i}`}
                className="rounded-DEFAULT border border-outline-variant/60 p-3"
              >
                <div className="flex flex-wrap items-baseline gap-2 mb-1">
                  <span className="font-label-caps text-[10px] uppercase text-on-surface-variant">
                    Cluster {i + 1}
                  </span>
                  <span className="font-data-mono text-data-mono text-[12px]">
                    {c.size} compound{c.size === 1 ? "" : "s"}
                  </span>
                  {c.median_pchembl != null ? (
                    <span className="text-[11px] text-on-surface-variant">
                      median pChEMBL = {c.median_pchembl}
                    </span>
                  ) : null}
                  {c.median_alogp != null ? (
                    <span className="text-[11px] text-on-surface-variant">
                      median AlogP = {c.median_alogp}
                    </span>
                  ) : null}
                </div>
                <code className="block font-data-mono text-[11px] text-on-surface break-all leading-snug">
                  {c.scaffold || <em className="text-on-surface-variant">acyclic / no ring</em>}
                </code>
                <div className="flex flex-wrap gap-1 mt-2 font-data-mono text-[10px] text-on-surface-variant">
                  {c.examples.map((ex) => (
                    <span key={ex} className="border border-outline-variant/50 rounded-sm px-1.5 py-0.5">
                      {ex}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </Panel>
      ) : null}

      {compounds.length === 0 ? (
        <p className="font-body-md text-body-md text-on-surface-variant">
          No compounds matched these criteria. Try widening the potency range or removing the
          organism filter.
        </p>
      ) : (
        <div className="overflow-x-auto -mx-2">
          <table className="w-full text-left border-collapse min-w-[680px]">
            <thead>
              <tr className="border-b border-outline-variant bg-surface-container-low font-label-caps text-label-caps text-on-surface-variant uppercase text-[10px]">
                <th className="p-2 pl-3">ChEMBL ID</th>
                <th className="p-2">Molecule</th>
                <th className="p-2">Target</th>
                <th className="p-2">Type</th>
                <th className="p-2 text-right">Value</th>
                <th className="p-2 text-right">pChEMBL</th>
                <th className="p-2 pr-3">Assay</th>
              </tr>
            </thead>
            <tbody className="font-data-mono text-data-mono text-on-surface text-[12px]">
              {compounds.map((c, i) => (
                <tr
                  key={`${c.chembl_id}-${i}`}
                  className={i % 2 === 1 ? "bg-surface-container-low/60 border-b border-outline-variant/40" : "border-b border-outline-variant/40"}
                >
                  <td className="p-2 pl-3 font-medium whitespace-nowrap">{c.chembl_id}</td>
                  <td className="p-2 max-w-[180px] truncate" title={c.molecule_name ?? ""}>
                    {c.molecule_name ?? "—"}
                  </td>
                  <td className="p-2 whitespace-nowrap">{c.target_pref_name ?? c.target_chembl_id ?? "—"}</td>
                  <td className="p-2 whitespace-nowrap">{c.standard_type ?? "—"}</td>
                  <td className="p-2 text-right whitespace-nowrap">
                    {c.standard_value != null
                      ? `${formatNum(c.standard_value)} ${c.standard_units ?? ""}`.trim()
                      : "—"}
                  </td>
                  <td className="p-2 text-right whitespace-nowrap">
                    {c.pchembl_value != null ? c.pchembl_value.toFixed(2) : "—"}
                  </td>
                  <td className="p-2 pr-3 whitespace-nowrap">{c.assay_type ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export function ChatPanel({ initialQuery }: { initialQuery?: string }) {
  const formId = useId();
  const formRef = useRef<HTMLFormElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const inFlightRef = useRef(false);
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [pending, setPending] = useState(false);

  /** Uses explicit `query` (from the textarea / FormData) so submit is never blocked by a stale React state snapshot. */
  const sendQuery = useCallback(async (raw: string) => {
    const query = raw.trim();
    if (!query || inFlightRef.current) return;

    inFlightRef.current = true;
    setPending(true);

    const userMsg: ChatMessage = { id: crypto.randomUUID(), role: "user", text: query };
    setMessages((m) => [...m, userMsg]);
    setInput("");

    try {
      const response = await postChat(query);
      setMessages((m) => [
        ...m,
        { id: crypto.randomUUID(), role: "assistant", response },
      ]);
    } catch (e) {
      const message = e instanceof Error ? e.message : "Request failed";
      setMessages((m) => [...m, { id: crypto.randomUUID(), role: "assistant", error: message }]);
    } finally {
      inFlightRef.current = false;
      setPending(false);
      textareaRef.current?.focus();
    }
  }, []);

  // Auto-submit when the page is opened with ?message=... in the URL
  useEffect(() => {
    if (initialQuery) {
      void sendQuery(initialQuery);
    }
    // run only once on mount
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const readMessageFromForm = (): string => {
    const el = textareaRef.current;
    if (el) return el.value;
    const form = formRef.current;
    if (form) return String(new FormData(form).get("message") ?? "");
    return "";
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key !== "Enter" || e.shiftKey) return;
    e.preventDefault();
    if (inFlightRef.current) return;
    const query = e.currentTarget.value.trim();
    if (!query) return;
    void sendQuery(query);
  };

  return (
    <div className="flex-1 overflow-hidden flex flex-col bg-surface-container-lowest">
      <div className="flex-1 overflow-y-auto p-6">
        <div className="max-w-4xl mx-auto w-full space-y-6">
          {messages.length === 0 && !pending ? (
            <p className="text-center font-body-md text-on-surface-variant py-12">
              Ask about a molecule, reaction, or target.
            </p>
          ) : null}

          {messages.map((msg) =>
            msg.role === "user" ? (
              <div key={msg.id} className="flex gap-4 justify-end">
                <div className="bg-surface-container-high text-on-surface p-4 rounded-lg rounded-tr-none max-w-2xl border border-outline-variant/30 shadow-sm">
                  <p className="font-body-md text-body-md whitespace-pre-wrap">{msg.text}</p>
                </div>
                <div className="w-8 h-8 rounded-full border border-outline-variant shrink-0 mt-1 bg-surface-container-high flex items-center justify-center font-label-caps text-[10px] text-on-surface-variant">
                  You
                </div>
              </div>
            ) : "error" in msg ? (
              <div key={msg.id} className="flex gap-4">
                <div className="w-8 h-8 rounded-full bg-error flex items-center justify-center shrink-0 mt-1">
                  <span className="material-symbols-outlined text-on-primary text-[16px]">error</span>
                </div>
                <div className="bg-red-50 border border-red-200 text-red-900 p-4 rounded-lg max-w-4xl font-body-md text-sm">
                  {msg.error}
                </div>
              </div>
            ) : (
              <div key={msg.id} className="flex gap-4">
                <div className="w-8 h-8 rounded-full bg-primary flex items-center justify-center shrink-0 mt-1">
                  <span className="material-symbols-outlined text-on-primary text-[16px]">smart_toy</span>
                </div>
                {msg.response.response_type === "report" ? (
                  <AssistantReport report={msg.response.report} />
                ) : msg.response.response_type === "target_report" ? (
                  <AssistantTargetReport response={msg.response} />
                ) : msg.response.response_type === "toxicity_risk_analysis" ? (
                  <AssistantToxicityRisk response={msg.response} />
                ) : (
                  <ValidationWarning
                    response={msg.response}
                    onSuggest={(name) => void sendQuery(name)}
                  />
                )}
              </div>
            ),
          )}

          {pending ? (
            <div className="flex gap-4">
              <div className="w-8 h-8 rounded-full bg-primary flex items-center justify-center shrink-0 mt-1 animate-pulse">
                <span className="material-symbols-outlined text-on-primary text-[16px]">hourglass_empty</span>
              </div>
              <div className="bg-surface-container-low border border-outline-variant rounded-lg px-4 py-3 font-body-md text-on-surface-variant">
                Running pipeline…
              </div>
            </div>
          ) : null}
        </div>
      </div>

      <div className="border-t border-outline-variant bg-surface-container-lowest p-4 px-6 shrink-0">
        <form
          id={formId}
          ref={formRef}
          className="max-w-4xl mx-auto relative flex items-end gap-2 min-w-0"
          onSubmit={(e) => {
            e.preventDefault();
            if (inFlightRef.current) return;
            const query = readMessageFromForm().trim();
            if (!query) return;
            void sendQuery(query);
          }}
        >
          <button
            type="button"
            className="p-3 shrink-0 text-on-surface-variant hover:text-primary transition-colors mb-1"
            aria-label="Attach file (not wired)"
          >
            <span className="material-symbols-outlined">attach_file</span>
          </button>
          <div className="min-w-0 flex-1 bg-surface-container-low border border-outline-variant rounded-xl overflow-hidden focus-within:border-primary focus-within:ring-1 focus-within:ring-primary transition-shadow">
            <textarea
              ref={textareaRef}
              name="message"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={onKeyDown}
              disabled={pending}
              autoComplete="off"
              className="w-full min-w-0 bg-transparent border-none focus:ring-0 resize-none p-3 font-body-md text-on-surface max-h-32 min-h-[48px] disabled:opacity-60"
              placeholder="Ask about a molecule, reaction, or target..."
              rows={2}
              aria-label="Chat message"
            />
          </div>
          <button
            type="submit"
            disabled={pending}
            className="p-3 shrink-0 bg-primary text-on-primary rounded-xl hover:bg-slate-800 transition-colors mb-1 flex items-center justify-center disabled:opacity-50 disabled:pointer-events-none"
            aria-label="Send message"
          >
            <span className="material-symbols-outlined">send</span>
          </button>
        </form>
        <div className="text-center mt-2">
          <span className="font-label-caps text-[10px] text-on-surface-variant uppercase">
            AI can produce inaccurate info. Verify vital molecular data.
          </span>
        </div>
      </div>
    </div>
  );
}
