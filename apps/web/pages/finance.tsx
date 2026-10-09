import { useEffect, useState, type FormEvent } from "react";
import Layout from "@/components/Layout";
import DashboardSummaryView from "@/components/DashboardSummaryView";
import { useAuth } from "@/lib/useAuth";
import { apiFetch } from "@/lib/api";
import type {
  DashboardSummary,
  Expense,
  Member,
  PaginatedExpenses,
  PaginatedIncome,
  PaginatedMembers,
  PaymentMethod,
} from "@/lib/types";

const PERIOD_OPTIONS: { value: string; label: string }[] = [
  { value: "today", label: "Today" },
  { value: "this_week", label: "This Week" },
  { value: "last_week", label: "Last Week" },
  { value: "this_month", label: "This Month" },
  { value: "last_month", label: "Last Month" },
  { value: "this_year", label: "This Year" },
  { value: "last_year", label: "Last Year" },
  { value: "custom", label: "Custom" },
];

const INCOME_CATEGORIES: { value: string; label: string }[] = [
  { value: "pt", label: "PT" },
  { value: "service", label: "Service" },
  { value: "product", label: "Product" },
];

const METHODS: { value: PaymentMethod; label: string }[] = [
  { value: "cash", label: "Cash" },
  { value: "card", label: "Card" },
  { value: "upi", label: "UPI" },
  { value: "other", label: "Other" },
];

const PAGE_SIZE = 25;

function todayISO(): string {
  return new Date().toISOString().slice(0, 10);
}

function periodParams(period: string, customFrom: string, customTo: string): URLSearchParams {
  const params = new URLSearchParams({ period });
  if (period === "custom") {
    params.set("from", customFrom);
    params.set("to", customTo);
  }
  return params;
}

function fmtMoney(n: number) {
  return `₹${n.toLocaleString()}`;
}

export default function FinancePage() {
  const { session, loading } = useAuth();

  const [period, setPeriod] = useState("this_month");
  const [customFrom, setCustomFrom] = useState(todayISO());
  const [customTo, setCustomTo] = useState(todayISO());

  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [summaryError, setSummaryError] = useState<string | null>(null);

  const [tab, setTab] = useState<"income" | "expense">("income");

  // Income tab
  const [income, setIncome] = useState<PaginatedIncome | null>(null);
  const [incomePage, setIncomePage] = useState(1);
  const [incomeError, setIncomeError] = useState<string | null>(null);
  const [showAddIncome, setShowAddIncome] = useState(false);
  const [incomeCategory, setIncomeCategory] = useState("pt");
  const [incomeMemberId, setIncomeMemberId] = useState("");
  const [memberFilter, setMemberFilter] = useState("");
  const [incomeAmount, setIncomeAmount] = useState("");
  const [incomeDiscount, setIncomeDiscount] = useState("0");
  const [incomeMethod, setIncomeMethod] = useState<PaymentMethod>("cash");
  const [incomeDate, setIncomeDate] = useState(todayISO());
  const [incomeNote, setIncomeNote] = useState("");
  const [incomeSaving, setIncomeSaving] = useState(false);
  const [incomeFormError, setIncomeFormError] = useState<string | null>(null);
  const [members, setMembers] = useState<Member[]>([]);

  // Expense tab
  const [expenses, setExpenses] = useState<PaginatedExpenses | null>(null);
  const [expensePage, setExpensePage] = useState(1);
  const [expenseError, setExpenseError] = useState<string | null>(null);
  const [showExpenseForm, setShowExpenseForm] = useState(false);
  const [editingExpense, setEditingExpense] = useState<Expense | null>(null);
  const [expenseCategory, setExpenseCategory] = useState("");
  const [expenseAmount, setExpenseAmount] = useState("");
  const [expenseDate, setExpenseDate] = useState(todayISO());
  const [expenseMode, setExpenseMode] = useState<PaymentMethod>("cash");
  const [expenseDescription, setExpenseDescription] = useState("");
  const [expenseSaving, setExpenseSaving] = useState(false);
  const [expenseFormError, setExpenseFormError] = useState<string | null>(null);
  const [categoryPresets, setCategoryPresets] = useState<string[]>([]);

  function loadSummary(token: string) {
    apiFetch<DashboardSummary>(`/dashboard/summary?${periodParams(period, customFrom, customTo)}`, { token })
      .then(setSummary)
      .catch((e) => setSummaryError(e instanceof Error ? e.message : "Could not load finance report"));
  }

  function loadIncome(token: string, page: number) {
    const params = periodParams(period, customFrom, customTo);
    params.set("page", String(page));
    params.set("page_size", String(PAGE_SIZE));
    apiFetch<PaginatedIncome>(`/dashboard/finance/income?${params}`, { token })
      .then((r) => {
        setIncome(r);
        setIncomePage(r.page);
        setIncomeError(null);
      })
      .catch((e) => setIncomeError(e instanceof Error ? e.message : "Could not load income"));
  }

  function loadExpenses(token: string, page: number) {
    const params = periodParams(period, customFrom, customTo);
    params.set("page", String(page));
    params.set("page_size", String(PAGE_SIZE));
    apiFetch<PaginatedExpenses>(`/expenses?${params}`, { token })
      .then((r) => {
        setExpenses(r);
        setExpensePage(r.page);
        setExpenseError(null);
      })
      .catch((e) => setExpenseError(e instanceof Error ? e.message : "Could not load expenses"));
  }

  function reloadAll(token: string) {
    loadSummary(token);
    loadIncome(token, 1);
    loadExpenses(token, 1);
  }

  // A period change (or applying a custom range) refreshes the summary AND
  // both tabs together, per spec — not just whichever tab happens to be
  // open, since switching tabs shouldn't trigger a fresh fetch of stale data.
  useEffect(() => {
    if (!session) return;
    if (period === "custom" && (!customFrom || !customTo)) return;
    reloadAll(session.access_token);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session, period, period === "custom" ? customFrom : null, period === "custom" ? customTo : null]);

  useEffect(() => {
    if (!session) return;
    apiFetch<string[]>("/expenses/categories", { token: session.access_token })
      .then(setCategoryPresets)
      .catch(() => {
        /* presets are a convenience, not required to use the form */
      });
    apiFetch<PaginatedMembers>("/members?page_size=500", { token: session.access_token })
      .then((r) => setMembers(r.items))
      .catch(() => {
        /* member picker on Add Income is optional anyway */
      });
  }, [session]);

  async function handleAddIncome(e: FormEvent) {
    e.preventDefault();
    if (!session) return;
    setIncomeSaving(true);
    setIncomeFormError(null);
    try {
      await apiFetch("/income", {
        method: "POST",
        token: session.access_token,
        body: {
          category: incomeCategory,
          member_id: incomeMemberId || undefined,
          amount: Number(incomeAmount),
          discount_amount: Number(incomeDiscount) || 0,
          method: incomeMethod,
          income_date: incomeDate || undefined,
          note: incomeNote || undefined,
        },
      });
      setShowAddIncome(false);
      setIncomeMemberId("");
      setMemberFilter("");
      setIncomeAmount("");
      setIncomeDiscount("0");
      setIncomeNote("");
      setIncomeDate(todayISO());
      reloadAll(session.access_token);
    } catch (err) {
      setIncomeFormError(err instanceof Error ? err.message : "Could not record income");
    } finally {
      setIncomeSaving(false);
    }
  }

  function startAddExpense() {
    setEditingExpense(null);
    setExpenseCategory("");
    setExpenseAmount("");
    setExpenseDate(todayISO());
    setExpenseMode("cash");
    setExpenseDescription("");
    setExpenseFormError(null);
    setShowExpenseForm(true);
  }

  function startEditExpense(expense: Expense) {
    setEditingExpense(expense);
    setExpenseCategory(expense.category);
    setExpenseAmount(String(expense.amount));
    setExpenseDate(expense.expense_date);
    setExpenseMode(expense.payment_mode);
    setExpenseDescription(expense.description ?? "");
    setExpenseFormError(null);
    setShowExpenseForm(true);
  }

  async function handleSaveExpense(e: FormEvent) {
    e.preventDefault();
    if (!session) return;
    setExpenseSaving(true);
    setExpenseFormError(null);
    try {
      const body = {
        category: expenseCategory,
        amount: Number(expenseAmount),
        expense_date: expenseDate || undefined,
        payment_mode: expenseMode,
        description: expenseDescription || undefined,
      };
      if (editingExpense) {
        await apiFetch(`/expenses/${editingExpense.id}`, { method: "PATCH", token: session.access_token, body });
      } else {
        await apiFetch("/expenses", { method: "POST", token: session.access_token, body });
      }
      setShowExpenseForm(false);
      reloadAll(session.access_token);
    } catch (err) {
      setExpenseFormError(err instanceof Error ? err.message : "Could not save expense");
    } finally {
      setExpenseSaving(false);
    }
  }

  async function handleDeleteExpense(expense: Expense) {
    if (!session) return;
    if (!window.confirm(`Delete this ${expense.category} expense of ${fmtMoney(expense.amount)}?`)) return;
    await apiFetch(`/expenses/${expense.id}`, { method: "DELETE", token: session.access_token });
    reloadAll(session.access_token);
  }

  const filteredMembers = memberFilter
    ? members.filter((m) => m.name.toLowerCase().includes(memberFilter.toLowerCase()))
    : members;

  if (loading || !session) {
    return (
      <main className="min-h-screen flex items-center justify-center">
        <p>Loading…</p>
      </main>
    );
  }

  return (
    <Layout>
      <div className="flex flex-col gap-6">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div>
            <h1 className="text-xl font-semibold text-gray-900">Finance Report</h1>
            <p className="text-sm text-gray-500">View income and expense reports</p>
          </div>
          <div className="flex items-center gap-2 text-sm flex-wrap">
            <select
              className="border rounded px-3 py-2"
              value={period}
              onChange={(e) => setPeriod(e.target.value)}
            >
              {PERIOD_OPTIONS.map((p) => (
                <option key={p.value} value={p.value}>
                  {p.label}
                </option>
              ))}
            </select>
            {period === "custom" && (
              <>
                <input
                  type="date"
                  className="border rounded px-2 py-2"
                  value={customFrom}
                  onChange={(e) => setCustomFrom(e.target.value)}
                />
                <span>–</span>
                <input
                  type="date"
                  className="border rounded px-2 py-2"
                  value={customTo}
                  onChange={(e) => setCustomTo(e.target.value)}
                />
              </>
            )}
          </div>
        </div>
        {summary && <p className="text-sm text-gray-500">{summary.range_label}</p>}

        {summaryError && <p className="text-red-600 text-sm">{summaryError}</p>}
        {summary ? (
          <DashboardSummaryView
            summary={summary}
            onMemberChanged={() => session && reloadAll(session.access_token)}
          />
        ) : (
          !summaryError && <p>Loading…</p>
        )}

        {/* Income / Expense tabs */}
        <div className="flex gap-2 border-b">
          <button
            onClick={() => setTab("income")}
            className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px ${
              tab === "income" ? "border-yellow-400 text-gray-900" : "border-transparent text-gray-500"
            }`}
          >
            Income
          </button>
          <button
            onClick={() => setTab("expense")}
            className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px ${
              tab === "expense" ? "border-yellow-400 text-gray-900" : "border-transparent text-gray-500"
            }`}
          >
            Expense
          </button>
        </div>

        {tab === "income" && (
          <div className="flex flex-col gap-4">
            <div className="flex items-center justify-between">
              <h2 className="font-semibold text-gray-900">Income transactions</h2>
              <button
                onClick={() => setShowAddIncome((v) => !v)}
                className="rounded bg-yellow-400 text-black px-3 py-1.5 text-sm"
              >
                {showAddIncome ? "Cancel" : "Add Income"}
              </button>
            </div>

            {showAddIncome && (
              <form onSubmit={handleAddIncome} className="border rounded p-4 flex flex-col gap-3">
                <div className="flex flex-wrap gap-3">
                  <label className="flex flex-col gap-1 text-sm">
                    Category
                    <select
                      className="border rounded px-3 py-2"
                      value={incomeCategory}
                      onChange={(e) => setIncomeCategory(e.target.value)}
                    >
                      {INCOME_CATEGORIES.map((c) => (
                        <option key={c.value} value={c.value}>
                          {c.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="flex flex-col gap-1 text-sm flex-1 min-w-[12rem]">
                    Member (optional)
                    <input
                      className="border rounded px-3 py-2"
                      placeholder="Search by name…"
                      value={memberFilter}
                      onChange={(e) => setMemberFilter(e.target.value)}
                    />
                    <select
                      className="border rounded px-3 py-2"
                      value={incomeMemberId}
                      onChange={(e) => setIncomeMemberId(e.target.value)}
                    >
                      <option value="">No member (walk-in sale)</option>
                      {filteredMembers.map((m) => (
                        <option key={m.id} value={m.id}>
                          {m.name}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
                <div className="flex flex-wrap gap-3">
                  <label className="flex flex-col gap-1 text-sm">
                    Amount
                    <input
                      type="number"
                      min={0.01}
                      step="0.01"
                      className="border rounded px-3 py-2 w-32"
                      value={incomeAmount}
                      onChange={(e) => setIncomeAmount(e.target.value)}
                      required
                    />
                  </label>
                  <label className="flex flex-col gap-1 text-sm">
                    Discount
                    <input
                      type="number"
                      min={0}
                      step="0.01"
                      className="border rounded px-3 py-2 w-28"
                      value={incomeDiscount}
                      onChange={(e) => setIncomeDiscount(e.target.value)}
                    />
                  </label>
                  <label className="flex flex-col gap-1 text-sm">
                    Mode
                    <select
                      className="border rounded px-3 py-2"
                      value={incomeMethod}
                      onChange={(e) => setIncomeMethod(e.target.value as PaymentMethod)}
                    >
                      {METHODS.map((m) => (
                        <option key={m.value} value={m.value}>
                          {m.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="flex flex-col gap-1 text-sm">
                    Date
                    <input
                      type="date"
                      className="border rounded px-3 py-2"
                      value={incomeDate}
                      onChange={(e) => setIncomeDate(e.target.value)}
                    />
                  </label>
                  <label className="flex flex-col gap-1 text-sm flex-1 min-w-[10rem]">
                    Note (optional)
                    <input
                      className="border rounded px-3 py-2"
                      value={incomeNote}
                      onChange={(e) => setIncomeNote(e.target.value)}
                    />
                  </label>
                </div>
                {incomeFormError && <p className="text-red-600 text-sm">{incomeFormError}</p>}
                <button
                  type="submit"
                  disabled={incomeSaving}
                  className="rounded bg-yellow-400 text-black py-2 text-sm disabled:opacity-50 self-start px-6"
                >
                  {incomeSaving ? "Saving…" : "Record income"}
                </button>
              </form>
            )}

            {incomeError && <p className="text-red-600 text-sm">{incomeError}</p>}
            <div className="overflow-x-auto rounded-2xl shadow-sm border border-gray-200 bg-white">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-black text-yellow-300 text-left">
                    <th className="p-2.5 font-medium">Date</th>
                    <th className="p-2.5 font-medium">Member</th>
                    <th className="p-2.5 font-medium">Type</th>
                    <th className="p-2.5 font-medium">Plan</th>
                    <th className="p-2.5 font-medium">Mode</th>
                    <th className="p-2.5 font-medium">Amount</th>
                    <th className="p-2.5 font-medium">Discount</th>
                  </tr>
                </thead>
                <tbody>
                  {(income?.items ?? []).map((t, i) => (
                    <tr key={t.id} className={i % 2 === 1 ? "bg-gray-50" : "bg-white"}>
                      <td className="p-2.5 text-gray-500 whitespace-nowrap">
                        {new Date(t.date).toLocaleDateString()}
                      </td>
                      <td className="p-2.5 text-gray-900">{t.member_name}</td>
                      <td className="p-2.5 text-gray-700">{t.transaction_type}</td>
                      <td className="p-2.5 text-gray-700">{t.plan_name ?? "—"}</td>
                      <td className="p-2.5 text-gray-700">{t.method}</td>
                      <td className="p-2.5 font-medium text-gray-900">{fmtMoney(t.amount)}</td>
                      <td className="p-2.5 text-gray-500">{t.discount_amount > 0 ? fmtMoney(t.discount_amount) : "—"}</td>
                    </tr>
                  ))}
                  {income && income.items.length === 0 && (
                    <tr>
                      <td colSpan={7} className="p-4 text-center text-gray-400">
                        No income transactions for this period.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
            {income && income.total > 0 && (
              <div className="flex items-center justify-between text-sm text-gray-500">
                <span>
                  Showing {(incomePage - 1) * PAGE_SIZE + 1}–{Math.min(incomePage * PAGE_SIZE, income.total)} of{" "}
                  {income.total}
                </span>
                <div className="flex gap-2">
                  <button
                    onClick={() => session && loadIncome(session.access_token, incomePage - 1)}
                    disabled={incomePage <= 1}
                    className="rounded border px-3 py-1.5 disabled:opacity-40"
                  >
                    Previous
                  </button>
                  <button
                    onClick={() => session && loadIncome(session.access_token, incomePage + 1)}
                    disabled={incomePage * PAGE_SIZE >= income.total}
                    className="rounded border px-3 py-1.5 disabled:opacity-40"
                  >
                    Next
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        {tab === "expense" && (
          <div className="flex flex-col gap-4">
            <div className="flex items-center justify-between">
              <h2 className="font-semibold text-gray-900">Expenses</h2>
              <button
                onClick={showExpenseForm ? () => setShowExpenseForm(false) : startAddExpense}
                className="rounded bg-yellow-400 text-black px-3 py-1.5 text-sm"
              >
                {showExpenseForm ? "Cancel" : "Add Expense"}
              </button>
            </div>

            {showExpenseForm && (
              <form onSubmit={handleSaveExpense} className="border rounded p-4 flex flex-wrap gap-3 items-end">
                <label className="flex flex-col gap-1 text-sm">
                  Date
                  <input
                    type="date"
                    className="border rounded px-3 py-2"
                    value={expenseDate}
                    onChange={(e) => setExpenseDate(e.target.value)}
                  />
                </label>
                <label className="flex flex-col gap-1 text-sm">
                  Category
                  <input
                    list="expense-category-presets"
                    className="border rounded px-3 py-2"
                    value={expenseCategory}
                    onChange={(e) => setExpenseCategory(e.target.value)}
                    required
                  />
                  <datalist id="expense-category-presets">
                    {categoryPresets.map((c) => (
                      <option key={c} value={c} />
                    ))}
                  </datalist>
                </label>
                <label className="flex flex-col gap-1 text-sm">
                  Amount
                  <input
                    type="number"
                    min={0.01}
                    step="0.01"
                    className="border rounded px-3 py-2 w-32"
                    value={expenseAmount}
                    onChange={(e) => setExpenseAmount(e.target.value)}
                    required
                  />
                </label>
                <label className="flex flex-col gap-1 text-sm">
                  Mode
                  <select
                    className="border rounded px-3 py-2"
                    value={expenseMode}
                    onChange={(e) => setExpenseMode(e.target.value as PaymentMethod)}
                  >
                    {METHODS.map((m) => (
                      <option key={m.value} value={m.value}>
                        {m.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="flex flex-col gap-1 text-sm flex-1 min-w-[12rem]">
                  Description (optional)
                  <input
                    className="border rounded px-3 py-2"
                    value={expenseDescription}
                    onChange={(e) => setExpenseDescription(e.target.value)}
                  />
                </label>
                {expenseFormError && <p className="text-red-600 text-sm w-full">{expenseFormError}</p>}
                <button
                  type="submit"
                  disabled={expenseSaving}
                  className="rounded bg-yellow-400 text-black px-4 py-2 text-sm disabled:opacity-50"
                >
                  {expenseSaving ? "Saving…" : editingExpense ? "Save changes" : "Add expense"}
                </button>
              </form>
            )}

            {expenseError && <p className="text-red-600 text-sm">{expenseError}</p>}
            <div className="overflow-x-auto rounded-2xl shadow-sm border border-gray-200 bg-white">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-black text-yellow-300 text-left">
                    <th className="p-2.5 font-medium">Date</th>
                    <th className="p-2.5 font-medium">Category</th>
                    <th className="p-2.5 font-medium">Mode</th>
                    <th className="p-2.5 font-medium">Description</th>
                    <th className="p-2.5 font-medium">Amount</th>
                    <th className="p-2.5 font-medium">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {(expenses?.items ?? []).map((ex, i) => (
                    <tr key={ex.id} className={i % 2 === 1 ? "bg-gray-50" : "bg-white"}>
                      <td className="p-2.5 text-gray-500 whitespace-nowrap">
                        {new Date(ex.expense_date).toLocaleDateString()}
                      </td>
                      <td className="p-2.5 text-gray-900">{ex.category}</td>
                      <td className="p-2.5 text-gray-700">{ex.payment_mode}</td>
                      <td className="p-2.5 text-gray-500">{ex.description || "—"}</td>
                      <td className="p-2.5 font-medium text-gray-900">{fmtMoney(ex.amount)}</td>
                      <td className="p-2.5">
                        <div className="flex gap-3">
                          <button onClick={() => startEditExpense(ex)} className="text-sm underline">
                            Edit
                          </button>
                          <button
                            onClick={() => handleDeleteExpense(ex)}
                            className="text-sm underline text-red-600"
                          >
                            Delete
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                  {expenses && expenses.items.length === 0 && (
                    <tr>
                      <td colSpan={6} className="p-4 text-center text-gray-400">
                        No expenses for this period.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
            {expenses && expenses.total > 0 && (
              <div className="flex items-center justify-between text-sm text-gray-500">
                <span>
                  Showing {(expensePage - 1) * PAGE_SIZE + 1}–{Math.min(expensePage * PAGE_SIZE, expenses.total)} of{" "}
                  {expenses.total}
                </span>
                <div className="flex gap-2">
                  <button
                    onClick={() => session && loadExpenses(session.access_token, expensePage - 1)}
                    disabled={expensePage <= 1}
                    className="rounded border px-3 py-1.5 disabled:opacity-40"
                  >
                    Previous
                  </button>
                  <button
                    onClick={() => session && loadExpenses(session.access_token, expensePage + 1)}
                    disabled={expensePage * PAGE_SIZE >= expenses.total}
                    className="rounded border px-3 py-1.5 disabled:opacity-40"
                  >
                    Next
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </Layout>
  );
}
