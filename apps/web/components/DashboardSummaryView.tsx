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

function StatCard({ icon, label, value, hero = false }: { icon: string; label: string; value: number; hero?: boolean }) {
  return (
    <div
      className={`rounded-2xl p-4 flex items-center gap-3 shadow-sm border ${
        hero
          ? "bg-gradient-to-br from-emerald-600 to-green-700 border-emerald-700 text-white"
          : "bg-white border-emerald-100 text-emerald-950"
      }`}
    >
      <span
        className={`shrink-0 w-10 h-10 rounded-full flex items-center justify-center text-lg ${
          hero ? "bg-white/15" : "bg-emerald-50"
        }`}
      >
        {icon}
      </span>
      <div className="flex flex-col">
        <span className={`text-xs ${hero ? "text-emerald-50/90" : "text-emerald-700/70"}`}>{label}</span>
        <span className="text-xl font-bold">{fmtMoney(value)}</span>
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
    <div className="rounded-xl p-3 flex flex-col gap-1 bg-emerald-50 border border-emerald-100">
      <span className="text-sm">
        {icon} <span className="text-emerald-800/80">{label}</span>
      </span>
      <span className="text-lg font-semibold text-emerald-900">{fmtMoney(amount)}</span>
      <span className="text-xs text-emerald-700/60">
        {count} {count === 1 ? "txn" : "txns"}
      </span>
    </div>
  );
}

/** Stat cards + category cards + recent-transactions table for a
 * DashboardSummary. Shared between "/" and "/finance" so the two pages
 * render identically, just fed different date ranges. Deliberately fixed
 * green/white — not the app's default theme-following palette — this is a
 * branded dashboard surface, not a general-purpose page. */
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
        <h2 className="font-semibold mb-2 text-emerald-900">Recent Transactions</h2>
        <div className="overflow-x-auto rounded-2xl shadow-sm border border-emerald-100 bg-white">
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
                <tr key={t.id} className={i % 2 === 1 ? "bg-emerald-50/60" : "bg-white"}>
                  <td className="p-2.5">
                    <span className={`text-white text-xs px-2 py-0.5 rounded-full ${TYPE_COLOR[t.transaction_type]}`}>
                      {TYPE_LABEL[t.transaction_type]}
                    </span>
                  </td>
                  <td className="p-2.5 text-emerald-900/60 whitespace-nowrap">
                    {new Date(t.date).toLocaleDateString()}
                  </td>
                  <td className="p-2.5 text-emerald-950">{t.plan_name}</td>
                  <td className="p-2.5 font-medium text-emerald-950">{fmtMoney(t.amount)}</td>
                  <td className="p-2.5">
                    {t.member_id ? (
                      <Link href={`/members/${t.member_id}`} className="underline text-emerald-700 hover:text-emerald-900">
                        {t.member_name}
                      </Link>
                    ) : (
                      <span className="text-emerald-950">{t.member_name}</span>
                    )}
                  </td>
                  <td className="p-2.5">
                    <span
                      className={`text-xs px-2 py-0.5 rounded-full border ${
                        t.method === "cash"
                          ? "border-emerald-900/20 text-emerald-900/70"
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
                  <td colSpan={6} className="p-4 text-center text-emerald-900/50">
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
