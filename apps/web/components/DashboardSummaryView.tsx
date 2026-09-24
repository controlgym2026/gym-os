import Link from "next/link";
import type { DashboardSummary, TransactionType } from "@/lib/types";

const TYPE_LABEL: Record<TransactionType, string> = {
  admission: "Admission",
  renewal: "Renewal",
  due_payment: "Due Payment",
};

const TYPE_COLOR: Record<TransactionType, string> = {
  admission: "bg-emerald-600",
  renewal: "bg-teal-600",
  due_payment: "bg-amber-500",
};

function fmtMoney(n: number) {
  return `₹${n.toLocaleString()}`;
}

// One consistent white card surface for every tile — color lives in the
// icon badge, the number, and (for Profit) a left accent bar, never in the
// card's own background. That's what keeps cards, table, and the page's
// white background reading as one theme instead of patches of white/
// light-green/dark floating on top of each other.
function StatCard({ icon, label, value, hero = false }: { icon: string; label: string; value: number; hero?: boolean }) {
  return (
    <div
      className={`rounded-2xl p-4 flex items-center gap-3 shadow-sm border bg-white border-gray-200 ${
        hero ? "border-l-4 border-l-emerald-600" : ""
      }`}
    >
      <span className="shrink-0 w-10 h-10 rounded-full flex items-center justify-center text-lg bg-emerald-50">
        {icon}
      </span>
      <div className="flex flex-col">
        <span className="text-xs text-gray-500">{label}</span>
        <span className={`text-xl font-bold ${hero ? "text-emerald-700" : "text-gray-900"}`}>{fmtMoney(value)}</span>
      </div>
    </div>
  );
}

function CategoryCard({
  icon,
  label,
  count,
  amount,
}: {
  icon: string;
  label: string;
  count: number;
  amount: number;
}) {
  return (
    <div className="rounded-xl p-3 flex flex-col gap-1 bg-white border border-gray-200 shadow-sm">
      <span className="text-sm">
        {icon} <span className="text-gray-500">{label}</span>
      </span>
      <span className="text-lg font-semibold text-emerald-700">{fmtMoney(amount)}</span>
      <span className="text-xs text-gray-400">
        {count} {count === 1 ? "txn" : "txns"}
      </span>
    </div>
  );
}

/** Stat cards + category cards + recent-transactions table for a
 * DashboardSummary. Shared between "/" and "/finance" so the two pages
 * render identically, just fed different date ranges. One white surface
 * throughout (matching the app's single fixed light theme) — green is an
 * accent (icons, numbers, badges), never a card background. */
export default function DashboardSummaryView({ summary }: { summary: DashboardSummary }) {
  return (
    <div className="flex flex-col gap-6 w-full">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatCard icon="💰" label="Profit" value={summary.profit} hero />
        <StatCard icon="📈" label="Income" value={summary.income} />
        <StatCard icon="📉" label="Expense" value={summary.expense} />
        <StatCard icon="🏷️" label="Discount" value={summary.discount_total} />
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
        <CategoryCard icon="🆕" label="Admissions" count={summary.admissions.count} amount={summary.admissions.amount} />
        <CategoryCard icon="🔁" label="Renewals" count={summary.renewals.count} amount={summary.renewals.amount} />
        <CategoryCard icon="⏳" label="Due Paid" count={summary.due_paid.count} amount={summary.due_paid.amount} />
        <CategoryCard icon="💳" label="Online" count={summary.online.count} amount={summary.online.amount} />
        <CategoryCard icon="💵" label="Cash" count={summary.cash.count} amount={summary.cash.amount} />
      </div>

      <div>
        <h2 className="font-semibold mb-2 text-gray-900">Recent Transactions</h2>
        <div className="overflow-x-auto rounded-2xl shadow-sm border border-gray-200 bg-white">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-emerald-600 text-white text-left">
                <th className="p-2.5 font-medium">Type</th>
                <th className="p-2.5 font-medium">Date</th>
                <th className="p-2.5 font-medium">Plan</th>
                <th className="p-2.5 font-medium">Amount</th>
                <th className="p-2.5 font-medium">Member</th>
                <th className="p-2.5 font-medium">Method</th>
              </tr>
            </thead>
            <tbody>
              {summary.recent_transactions.map((t, i) => (
                <tr key={t.id} className={i % 2 === 1 ? "bg-gray-50" : "bg-white"}>
                  <td className="p-2.5">
                    <span className={`text-white text-xs px-2 py-0.5 rounded-full ${TYPE_COLOR[t.transaction_type]}`}>
                      {TYPE_LABEL[t.transaction_type]}
                    </span>
                  </td>
                  <td className="p-2.5 text-gray-500 whitespace-nowrap">{new Date(t.date).toLocaleDateString()}</td>
                  <td className="p-2.5 text-gray-900">{t.plan_name}</td>
                  <td className="p-2.5 font-medium text-gray-900">{fmtMoney(t.amount)}</td>
                  <td className="p-2.5">
                    {t.member_id ? (
                      <Link href={`/members/${t.member_id}`} className="underline text-emerald-700 hover:text-emerald-900">
                        {t.member_name}
                      </Link>
                    ) : (
                      <span className="text-gray-900">{t.member_name}</span>
                    )}
                  </td>
                  <td className="p-2.5">
                    <span
                      className={`text-xs px-2 py-0.5 rounded-full border ${
                        t.method === "cash"
                          ? "border-gray-300 text-gray-600"
                          : "border-emerald-600 text-emerald-700 bg-emerald-50"
                      }`}
                    >
                      {t.method === "cash" ? "Cash" : "Online"}
                    </span>
                  </td>
                </tr>
              ))}
              {summary.recent_transactions.length === 0 && (
                <tr>
                  <td colSpan={6} className="p-4 text-center text-gray-400">
                    No transactions yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
