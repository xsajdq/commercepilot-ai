const COLORS: Record<string, string> = {
  connected: "bg-green-100 text-green-800",
  active: "bg-green-100 text-green-800",
  success: "bg-green-100 text-green-800",
  approved: "bg-green-100 text-green-800",
  disconnected: "bg-gray-100 text-gray-700",
  draft: "bg-gray-100 text-gray-700",
  proposed: "bg-gray-100 text-gray-700",
  pending_approval: "bg-amber-100 text-amber-800",
  executing: "bg-amber-100 text-amber-800",
  error: "bg-red-100 text-red-800",
  failed: "bg-red-100 text-red-800",
  rejected: "bg-red-100 text-red-800",
  low: "bg-green-100 text-green-800",
  medium: "bg-amber-100 text-amber-800",
  high: "bg-red-100 text-red-800",
};

export default function StatusBadge({ value }: { value: string }) {
  const color = COLORS[value] ?? "bg-gray-100 text-gray-700";
  return (
    <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${color}`}>
      {value.replace(/_/g, " ")}
    </span>
  );
}
