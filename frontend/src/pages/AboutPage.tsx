import { Link } from "react-router-dom";
import {
  Microscope,
  FileText,
  Beaker,
  BarChart3,
  Lightbulb,
  Layers,
  Cpu,
  Database,
  ShieldCheck,
  Sparkles,
  Workflow,
  ArrowRight,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

export default function AboutPage() {
  return (
    <div className="max-w-5xl mx-auto">
      {/* Hero */}
      <div className="rounded-2xl bg-gradient-to-br from-brand-700 via-brand-800 to-brand-950 text-white p-8 md:p-10 shadow-sm overflow-hidden relative">
        <div className="absolute -right-10 -top-10 w-64 h-64 rounded-full bg-white/5 blur-3xl" />
        <div className="absolute -left-10 -bottom-16 w-72 h-72 rounded-full bg-accent-500/10 blur-3xl" />
        <div className="relative">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-white/10 backdrop-blur-sm text-xs font-medium">
            <Sparkles className="w-3.5 h-3.5" />
            Biomarker Intelligence Platform
          </div>
          <h1 className="mt-4 text-3xl md:text-4xl font-semibold leading-tight">
            Turn oncology research papers into{" "}
            <span className="text-accent-500">structured biomarker data</span>
          </h1>
          <p className="mt-3 text-brand-100 text-base md:text-lg max-w-3xl leading-relaxed">
            LitExtract reads a PDF, classifies the study, and runs four specialized
            extraction agents to deliver a clean four-sheet workbook your research,
            regulatory, and analytics teams can use immediately.
          </p>
          <div className="mt-6 flex flex-wrap gap-3">
            <Link
              to="/upload"
              className="inline-flex items-center gap-1.5 bg-white text-brand-800 px-4 py-2 rounded-lg text-sm font-medium hover:bg-brand-50"
            >
              Try it now <ArrowRight className="w-4 h-4" />
            </Link>
            <Link
              to="/history"
              className="inline-flex items-center gap-1.5 bg-white/10 text-white border border-white/20 px-4 py-2 rounded-lg text-sm font-medium hover:bg-white/15"
            >
              View past extractions
            </Link>
          </div>
        </div>
      </div>

      {/* What it extracts */}
      <Section
        title="What gets extracted"
        subtitle="Every uploaded paper produces four structured sheets, one per data type."
      >
        <div className="grid md:grid-cols-2 gap-4">
          <FeatureCard
            icon={FileText}
            tone="brand"
            title="Study Details"
            text="Study design, disease, patient counts, demographics, geography, follow-up duration, inclusion / exclusion, treatment regimen, staging."
          />
          <FeatureCard
            icon={Beaker}
            tone="emerald"
            title="BM Details"
            text="Biomarker catalog: name, type (RNA / Protein / Genetic / Clinical / Composite), biological nature, and standardized name forms."
          />
          <FeatureCard
            icon={BarChart3}
            tone="brand"
            title="BM Results"
            text="Statistical findings per biomarker × outcome: p-values, effect sizes, hazard ratios, confidence intervals, specimen, methodology."
          />
          <FeatureCard
            icon={Lightbulb}
            tone="emerald"
            title="Inferences"
            text="Author conclusions per biomarker — prognostic, diagnostic, predictive, monitoring claims with the supporting evidence statement."
          />
        </div>
      </Section>

      {/* Pipeline */}
      <Section
        title="How it works"
        subtitle="Five stages, fully automated. Each stage is observable and re-runnable."
      >
        <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
          <PipelineStep n={1} icon={FileText} title="Read PDF" text="Local extraction with PyMuPDF + pdfplumber. Pages, tables, layout preserved." />
          <PipelineStep n={2} icon={Workflow} title="Classify" text="Detect disease (17 types), study type (5), and biomarker type (3) by keyword scoring." />
          <PipelineStep n={3} icon={Layers} title="Compose prompt" text="4-level hierarchy: core + disease + study type + biomarker type addons." />
          <PipelineStep n={4} icon={Cpu} title="Run agents" text="Four specialized LLM agents extract in parallel where safe." />
          <PipelineStep n={5} icon={Database} title="Persist" text="Excel workbook + SQLite run history for audit and traceability." />
        </div>
      </Section>

      {/* Capabilities */}
      <Section title="Built for pharma research" subtitle="Designed around the things teams actually care about.">
        <div className="grid md:grid-cols-3 gap-4">
          <Capability
            icon={Microscope}
            title="Disease-aware prompts"
            text="Lung, breast, liver, gastric, thyroid, colorectal, pancreatic and more — each disease layers on its own extraction rules and abbreviations."
          />
          <Capability
            icon={ShieldCheck}
            title="Auditable runs"
            text="Every paper, every agent call, every cost — recorded in SQLite with the exact prompt hash so any result can be reproduced or compared."
          />
          <Capability
            icon={Sparkles}
            title="Cost-controlled"
            text="Defaults to gpt-4o-mini for ~16× lower cost than gpt-4o. Per-paper cost is reported on the dashboard so you always know what you spent."
          />
        </div>
      </Section>

      {/* Workflow card */}
      <Section title="Get started in seconds" subtitle="No setup beyond uploading a PDF.">
        <div className="rounded-2xl border border-slate-200 bg-white p-6">
          <ol className="space-y-3">
            <Step n={1} text="Open the Upload tab and drop a PDF (or click to browse)." />
            <Step n={2} text="Watch the four-stage progress: Upload → Read → Run agents → Compile." />
            <Step n={3} text="Review the four extracted tabs and download the Excel workbook." />
            <Step n={4} text="Find every past run in the History tab — searchable, downloadable, traceable." />
          </ol>
          <Link
            to="/upload"
            className="mt-6 inline-flex items-center gap-1.5 bg-brand-600 hover:bg-brand-700 text-white px-4 py-2 rounded-lg text-sm font-medium"
          >
            Upload your first paper <ArrowRight className="w-4 h-4" />
          </Link>
        </div>
      </Section>

      {/* Footer signature */}
      <div className="my-10 text-center text-xs text-slate-500">
        LitExtract · Biomarker Intelligence · v0.1
      </div>
    </div>
  );
}

function Section({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="mt-10">
      <div className="mb-4">
        <h2 className="text-xl font-semibold text-slate-900">{title}</h2>
        {subtitle ? <p className="mt-1 text-sm text-slate-500">{subtitle}</p> : null}
      </div>
      {children}
    </section>
  );
}

function FeatureCard({
  icon: Icon,
  title,
  text,
  tone,
}: {
  icon: LucideIcon;
  title: string;
  text: string;
  tone: "brand" | "emerald";
}) {
  const ring =
    tone === "brand" ? "ring-brand-100" : "ring-emerald-100";
  const iconBg =
    tone === "brand" ? "bg-brand-100 text-brand-700" : "bg-emerald-100 text-emerald-700";
  return (
    <div className={`rounded-xl border border-slate-200 bg-white p-5 ring-4 ${ring}/40`}>
      <div className="flex items-start gap-3">
        <div className={`w-10 h-10 rounded-lg grid place-items-center ${iconBg}`}>
          <Icon className="w-5 h-5" />
        </div>
        <div className="min-w-0">
          <div className="text-sm font-semibold text-slate-900">{title}</div>
          <div className="mt-1 text-sm text-slate-600 leading-relaxed">{text}</div>
        </div>
      </div>
    </div>
  );
}

function PipelineStep({
  n,
  icon: Icon,
  title,
  text,
}: {
  n: number;
  icon: LucideIcon;
  title: string;
  text: string;
}) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 relative">
      <div className="absolute -top-2 left-3 px-1.5 text-[10px] font-semibold tracking-wide text-brand-700 bg-white">
        STEP {n}
      </div>
      <div className="w-8 h-8 rounded-md bg-brand-50 text-brand-700 grid place-items-center mb-2.5">
        <Icon className="w-4 h-4" />
      </div>
      <div className="text-sm font-semibold text-slate-900">{title}</div>
      <div className="mt-1 text-xs text-slate-600 leading-relaxed">{text}</div>
    </div>
  );
}

function Capability({
  icon: Icon,
  title,
  text,
}: {
  icon: LucideIcon;
  title: string;
  text: string;
}) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5">
      <div className="w-9 h-9 rounded-md bg-slate-100 text-slate-700 grid place-items-center mb-3">
        <Icon className="w-4 h-4" />
      </div>
      <div className="text-sm font-semibold text-slate-900">{title}</div>
      <div className="mt-1 text-sm text-slate-600 leading-relaxed">{text}</div>
    </div>
  );
}

function Step({ n, text }: { n: number; text: string }) {
  return (
    <li className="flex items-start gap-3">
      <div className="shrink-0 w-6 h-6 rounded-full bg-brand-100 text-brand-700 grid place-items-center text-xs font-semibold tabular-nums">
        {n}
      </div>
      <div className="text-sm text-slate-700 leading-relaxed">{text}</div>
    </li>
  );
}
