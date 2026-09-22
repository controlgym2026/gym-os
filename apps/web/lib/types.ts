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

export type Member = {
  id: string;
  tenant_id: string;
  branch_id: string | null;
  name: string;
  phone: string | null;
  email: string | null;
  photo_url: string | null;
  biometric_ref: string | null;
  biometric_consent: boolean;
  biometric_consent_at: string | null;
  created_at: string;
  deleted_at: string | null;
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
  created_at: string;
};
