export type DashboardBucket = { count: number; amount: number };

export type PaymentMethod = "cash" | "card" | "upi" | "other";

// admission/renewal/due_payment come from a subscription payment;
// pt/service/product (Phase 6) are standalone sales, not tied to one.
export type TransactionType = "admission" | "renewal" | "due_payment" | "pt" | "service" | "product";

export type RecentTransaction = {
  id: string;
  transaction_type: TransactionType;
  date: string;
  plan_name: string | null; // null for pt/service/product — no subscription to name
  amount: number;
  discount_amount: number;
  member_id: string | null;
  member_name: string;
  method: PaymentMethod;
  gateway_ref: string | null; // manual reference, or the "note" on pt/service/product
};

// "today" | "this_week" | "last_week" | "this_month" | "last_month" |
// "this_year" | "last_year" | "custom" — kept as plain string on the
// frontend (matches how the API takes it) rather than re-declaring the
// literal union in two places.
export type FinancePeriod = string;

export type DashboardSummary = {
  range: { from: string; to: string };
  range_label: string; // e.g. "Oct 01, 2026 - Oct 31, 2026"
  profit: number;
  income: number;
  expense: number;
  discount_total: number;
  admissions: DashboardBucket;
  renewals: DashboardBucket;
  due_paid: DashboardBucket;
  pt: DashboardBucket;
  service: DashboardBucket;
  product: DashboardBucket;
  online: DashboardBucket;
  cash: DashboardBucket;
  recent_transactions: RecentTransaction[];
};

export type PaginatedIncome = {
  items: RecentTransaction[];
  total: number;
  page: number;
  page_size: number;
};

export type Expense = {
  id: string;
  tenant_id: string;
  category: string;
  amount: number;
  expense_date: string;
  payment_mode: PaymentMethod;
  description: string | null;
  created_by: string | null;
  created_at: string;
};

export type PaginatedExpenses = {
  items: Expense[];
  total: number;
  page: number;
  page_size: number;
};

export type BillingStatus = "active" | "trial" | "suspended" | "cancelled";

export type Tenant = {
  id: string;
  name: string;
  plan_tier: string;
  billing_status: BillingStatus;
  created_at: string;
  member_count: number;
  active_subscription_count: number;
  device_count: number;
  branch_count: number;
  // Livnexa Care's own commercial relationship with this gym — separate
  // from the gym's own member subscriptions/payments above.
  subscription_expires_at: string | null;
  subscription_days_remaining: number | null; // null when subscription_expires_at is null
  amount_paid: number;
  member_limit: number | null; // null = unlimited/not set
  device_limit: number | null;
  branch_limit: number | null;
};

export type TenantAuditLogEntry = {
  id: string;
  tenant_id: string;
  action: string;
  performed_by: string;
  note: string | null;
  created_at: string;
};

export type TenantStaffSummary = {
  id: string;
  role: string;
  branch_id: string | null;
  email: string | null;
};

export type TenantDetail = Tenant & {
  branches: { id: string; address: string | null; timezone: string }[];
  staff: TenantStaffSummary[];
  audit_log: TenantAuditLogEntry[];
};

export type PaginatedMembers = {
  items: Member[];
  total: number;
  page: number;
  page_size: number;
};

export type MemberImportResult = {
  imported: number;
  subscriptions_started: number;
  skipped: { line: number; reason: string }[];
  plan_warnings: { line: number; plan_name: string; reason: string }[];
};

export type CurrentSubscriptionSummary = {
  id: string;
  plan_id: string;
  plan_name: string;
  status: SubscriptionStatus;
  start_date: string;
  end_date: string | null;
  due_amount: number;
  sessions_remaining: number | null;
};

export type Member = {
  id: string;
  tenant_id: string;
  branch_id: string | null;
  // Permanent, human-readable, per-gym sequential ID — distinct from `id`
  // (the UUID). Assigned once, server-side only; never client-supplied.
  member_number: number;
  name: string;
  phone: string | null;
  email: string | null;
  photo_url: string | null;
  biometric_ref: string | null;
  biometric_consent: boolean;
  biometric_consent_at: string | null;
  created_at: string;
  deleted_at: string | null;
  // Only present on GET /members (the list) — attached server-side so the
  // list doesn't need an N+1 request per row. Undefined on GET /members/{id}.
  current_subscription?: CurrentSubscriptionSummary | null;
};

export type AttendanceUnmatched = {
  id: string;
  tenant_id: string;
  device_id: string;
  member_id: string | null; // set when a matched member's check-in was rejected; null for an unmatched PIN
  raw_pin: string;
  raw_timestamp: string;
  reason: string; // 'unmatched_pin' | a check_in_allowed() denial reason, e.g. 'subscription is frozen'
  received_at: string;
};

export type Device = {
  id: string;
  tenant_id: string;
  branch_id: string;
  vendor: string;
  serial_number: string;
  label: string | null;
  last_seen_at: string | null;
  status: "active" | "inactive";
  online: boolean; // computed by the API: last_seen_at within ~10 minutes
  created_at: string;
};

export type MembershipPlan = {
  id: string;
  tenant_id: string;
  name: string;
  duration_days: number;
  price: number;
  session_limit: number | null;
  is_active: boolean;
  created_at: string;
};

export type SubscriptionStatus = "ACTIVE" | "FROZEN" | "EXPIRED" | "CANCELLED";

export type Subscription = {
  id: string;
  tenant_id: string;
  member_id: string;
  plan_id: string;
  start_date: string;
  end_date: string | null;
  sessions_remaining: number | null;
  status: SubscriptionStatus;
  auto_renew: boolean;
  due_amount: number;
  frozen_at: string | null;
  created_at: string;
};

export type Attendance = {
  id: string;
  tenant_id: string;
  member_id: string;
  branch_id: string | null;
  device_id: string | null;
  checked_in_at: string;
  source: "manual" | "qr" | "biometric" | "mobile";
  created_at: string;
};

export type Payment = {
  id: string;
  tenant_id: string;
  subscription_id: string;
  amount: number;
  method: "cash" | "card" | "upi" | "other";
  gateway_ref: string | null;
  status: "pending" | "completed" | "failed" | "refunded";
  transaction_type: TransactionType;
  discount_amount: number;
  created_at: string;
};
