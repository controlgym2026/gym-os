import Link from "next/link";
import type { DashboardSummary, TransactionType } from "@/lib/types";

const TYPE_LABEL: Record<TransactionType, string> = {
  admission: "Admission",
  renewal: "Renewal",
  due_payment: "Due Payment",
};

const TYPE_COLOR: Record<TransactionType, string> = {
  admission: "bg-green-600",
  renewal: "bg-blue-600",
  due_payment: "bg-amber-600",
};

function fmtMoney(n: number) {
  return `₹${n.toLocaleString()}`;
}

function StatCard({ label, value }: { label: string; value: number }) {
  return (
    <div className="border rounded p-4 flex flex-col gap-1">
      <span className="text-sm opacity-70">{label}</span>
      <span className="text-2xl font-semibold">{fmtMoney(value)}</span>
    </div>
  );
}

function CategoryCard({ label, count, amount }: { label: string; count: number; amount: number }) {
  return (
    <div className="border rounded p-4 flex flex-col gap-1">
      <span className="text-sm opacity-70">{label}</span>
      <span className="text-lg font-semibold">{fmtMoney(amount)}</span>
      <span className="text-xs opacity-60">
        {count} {count === 1 ? "txn" : "txns"}
      </span>
    </div>
  );
}

/** Stat cards + category cards + recent-transactions table for a
 * DashboardSummary. Shared between "/" and "/finance" so the two pages
 * render identically, just fed different date ranges. */
export default function DashboardSummaryView({ summary }: { summary: DashboardSummary }) {
  return (
    <div className="flex flex-col gap-6 w-full">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatCard label="Profit" value={summary.profit} />
        <StatCard label="Income" value={summary.income} />
        <StatCard label="Expense" value={summary.expense} />
        <StatCard label="Discount" value={summary.discount_total} />
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
        <CategoryCard label="Admissions" count={summary.admissions.count} amount={summary.admissions.amount} />
        <CategoryCard label="Renewals" count={summary.renewals.count} amount={summary.renewals.amount} />
        <CategoryCard label="Due Paid" count={summary.due_paid.count} amount={summary.due_paid.amount} />
        <CategoryCard label="Online" count={summary.online.count} amount={summary.online.amount} />
        <CategoryCard label="Cash" count={summary.cash.count} amount={summary.cash.amount} />
      </div>

      <div>
        <h2 className="font-semibold mb-2">Recent Transactions</h2>
        <div className="overflow-x-auto border rounded">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left">
                <th className="p-2">Type</th>
                <th className="p-2">Date</th>
                <th className="p-2">Plan</th>
                <th className="p-2">Amount</th>
                <th className="p-2">Member</th>
                <th className="p-2">Method</th>
              </tr>
            </thead>
            <tbody>
              {summary.recent_transactions.map((t) => (
                <tr key={t.id} className="border-b last:border-0">
                  <td className="p-2">
                    <span className={`text-white text-xs px-2 py-0.5 rounded ${TYPE_COLOR[t.transaction_type]}`}>
                      {TYPE_LABEL[t.transaction_type]}
                    </span>
                  </td>
                  <td className="p-2 opacity-70 whitespace-nowrap">{new Date(t.date).toLocaleDateString()}</td>
                  <td className="p-2">{t.plan_name}</td>
                  <td className="p-2">{fmtMoney(t.amount)}</td>
                  <td className="p-2">
                    {t.member_id ? (
                      <Link href={`/members/${t.member_id}`} className="underline">
                        {t.member_name}
                      </Link>
                    ) : (
                      t.member_name
                    )}
                  </td>
                  <td className="p-2">
                    <span className="text-xs px-2 py-0.5 rounded border">
                      {t.method === "cash" ? "Cash" : "Online"}
                    </span>
                  </td>
                </tr>
              ))}
              {summary.recent_transactions.length === 0 && (
                <tr>
                  <td colSpan={6} className="p-3 text-center opacity-70">
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
