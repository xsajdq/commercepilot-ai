const COLORS: Record<string, { bg: string; text: string; dot: string }> = {
  connected: { bg: "bg-emerald-50", text: "text-emerald-700", dot: "bg-emerald-500" },
  active: { bg: "bg-emerald-50", text: "text-emerald-700", dot: "bg-emerald-500" },
  success: { bg: "bg-emerald-50", text: "text-emerald-700", dot: "bg-emerald-500" },
  succeeded: { bg: "bg-emerald-50", text: "text-emerald-700", dot: "bg-emerald-500" },
  approved: { bg: "bg-emerald-50", text: "text-emerald-700", dot: "bg-emerald-500" },
  disconnected: { bg: "bg-slate-100", text: "text-slate-600", dot: "bg-slate-400" },
  draft: { bg: "bg-slate-100", text: "text-slate-600", dot: "bg-slate-400" },
  proposed: { bg: "bg-slate-100", text: "text-slate-600", dot: "bg-slate-400" },
  queued: { bg: "bg-slate-100", text: "text-slate-600", dot: "bg-slate-400" },
  pending_approval: { bg: "bg-amber-50", text: "text-amber-700", dot: "bg-amber-500" },
  executing: { bg: "bg-amber-50", text: "text-amber-700", dot: "bg-amber-500" },
  running: { bg: "bg-amber-50", text: "text-amber-700", dot: "bg-amber-500" },
  error: { bg: "bg-rose-50", text: "text-rose-700", dot: "bg-rose-500" },
  failed: { bg: "bg-rose-50", text: "text-rose-700", dot: "bg-rose-500" },
  rejected: { bg: "bg-rose-50", text: "text-rose-700", dot: "bg-rose-500" },
  low: { bg: "bg-emerald-50", text: "text-emerald-700", dot: "bg-emerald-500" },
  medium: { bg: "bg-amber-50", text: "text-amber-700", dot: "bg-amber-500" },
  high: { bg: "bg-rose-50", text: "text-rose-700", dot: "bg-rose-500" },
};

export default function StatusBadge({ value }: { value: string }) {
  const c = COLORS[value] ?? { bg: "bg-slate-100", text: "text-slate-600", dot: "bg-slate-400" };
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide ${c.bg} ${c.text}`}
    >
      <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${c.dot}`} />
      {value.replace(/_/g, " ")}
    </span>
  );
}
