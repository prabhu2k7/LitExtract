import { Settings, ShieldCheck, BookOpen, FileLock2 } from "lucide-react";
import ApiKeyForm from "../components/ApiKeyForm";

export default function SettingsPage() {
  return (
    <div className="max-w-3xl mx-auto fade-in">
      <div className="mb-6 flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-slate-100 grid place-items-center">
          <Settings className="w-5 h-5 text-slate-700" />
        </div>
        <div>
          <h1 className="text-2xl font-semibold text-slate-900 tracking-tight">
            Settings
          </h1>
          <p className="text-sm text-slate-500">
            API keys and connection.
          </p>
        </div>
      </div>

      {/* API key card */}
      <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <ApiKeyForm />
      </div>

      {/* Privacy / how-we-handle-it */}
      <div className="mt-6 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex items-center gap-2 text-sm font-semibold text-slate-900">
          <ShieldCheck className="w-4 h-4 text-emerald-600" />
          How your key is handled
        </div>
        <ol className="mt-3 space-y-2 text-sm text-slate-700">
          <PrivacyPoint
            icon={FileLock2}
            title="Stored only in your browser"
            body="The key lives in localStorage (or sessionStorage if you opted out). Anyone with access to your browser can read it."
          />
          <PrivacyPoint
            icon={ShieldCheck}
            title="Sent only as a request header"
            body="On each upload we send X-OpenAI-Api-Key over TLS. The LitExtract server never writes it to disk, database, or logs."
          />
          <PrivacyPoint
            icon={BookOpen}
            title="Auditable"
            body="Search for litextract.openai_key in the frontend and X-OpenAI-Api-Key in the backend — those are the only places the key appears."
          />
        </ol>
      </div>
    </div>
  );
}

function PrivacyPoint({
  icon: Icon,
  title,
  body,
}: {
  icon: typeof ShieldCheck;
  title: string;
  body: string;
}) {
  return (
    <li className="flex items-start gap-2.5">
      <div className="w-7 h-7 rounded-md bg-slate-100 grid place-items-center shrink-0 mt-0.5">
        <Icon className="w-3.5 h-3.5 text-slate-700" />
      </div>
      <div>
        <div className="font-medium text-slate-900">{title}</div>
        <div className="text-xs text-slate-500 leading-relaxed">{body}</div>
      </div>
    </li>
  );
}
