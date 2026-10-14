# Gym Control (gym-os) — Requirements & Build Log

A record of what was asked for while building Gym Control, and what was built in response.
Reconstructed from the git history (76 commits, 2026-09-04 → 2026-10-14) plus the working
sessions. Dates are commit dates; short hashes point at the change in git.

- **Product:** Gym Control — gym member & membership-plan management SaaS with face-biometric
  attendance. A product of Livnexa Care Pvt Ltd.
- **Repo:** `controlgym2026/gym-os` (private) · monorepo: `apps/web` (Next.js 15, Pages Router,
  TypeScript, Tailwind v4) + `apps/api` (FastAPI, Python)
- **Hosting:** Web on Vercel · API on Render · Postgres/Auth/Storage on Supabase · email via Resend

---

## 1. Ground rules for how the work is done

| Requirement | How it's handled |
|---|---|
| Separate accounts per venture — never reuse CryoRevive/LivnexaLabs accounts | Gym Control has its own GitHub (`controlgym2026`), Supabase, Render and Vercel accounts; repo-local commit identity `Gym Control <controlgym2026@gmail.com>` |
| Work in phases and check in between them; ask on anything needing a browser login or a decision | Setup was done in 5 phases with a stop after each |
| npm always with `--legacy-peer-deps` | Enforced by `apps/web/.npmrc` |
| Backend always run as `python -m uvicorn …` | `apps/api/run.sh` follows this |
| Stay on free tiers where possible | Free stack; note that Render free tier sleeps, so live biometric pushes will need the paid Starter tier |
| Changes to live data or pushes to production only after confirmation | Followed throughout; data corrections are backed up first |

## 2. Platform setup (Sep 4 – Sep 12)

| Requirement | Response |
|---|---|
| Monorepo scaffold, both apps running | Next.js + FastAPI scaffold, `/health` endpoint, private GitHub repo |
| Multi-tenant database, every gym's data isolated | Supabase schema with `tenant_id` on every table and RLS policies (Tenant, Branch, Member, MembershipPlan, Subscription, Attendance, Device, Payment, Staff) |
| Backend hosting | Render Blueprint (`render.yaml`) |
| File storage for member photos | Started on Cloudflare R2, switched to Supabase Storage — `member-media` bucket with tenant_id policies |
| Frontend hosting + transactional email | Vercel + Resend configuration |
| Login and self-serve signup | Supabase Auth, signup flow, "Name your gym" bootstrap that creates the tenant and makes the user its owner |

## 3. Member management (Sep 22 – Oct 11)

| Requirement | Response |
|---|---|
| Add/list/search members, plans, subscriptions, payments | Phase 1 MVP: API endpoints + pages for members, membership plans, subscriptions, payment logging, manual check-in |
| Bulk-load existing members | `POST /members/import` CSV import (name, phone, email, plan_name); batched so 320 rows import in ~2.3s; shows the exact reason a row's plan didn't match |
| Large member list must stay fast | Paginated `GET /members` with indexes; per-page size selector |
| GymOps-style list + details popup | Members table with a Member Details popup (Early Renew, Edit Membership, Pause/Resume, Transaction History, Edit Member); member names on Dashboard/Finance/Unmatched open the same popup |
| Edit a member's name/phone/email | "Edit Member" (phone must be unique within the gym) |
| Enrol a new member with plan + payment in one step | Add-member form includes plan, start date, amount paid, discount, payment method |
| Member photos from webcam or phone | Photo capture (camera or file), square-cropped and compressed before upload; bigger square photo on the profile |
| Filters | Status (Active / Expiring in 7 days / Expired / Due / Paid), Has photo / No photo, Plan — combined with AND |
| Expired members must stand out | Red highlight with "Expired Nd ago"; Expired filter sorted by most recently lapsed |
| Human-readable member IDs | Sequential `member_number`; active members renumbered 1..349 |
| Show final price when a discount is given | Highlighted "Final price" and "Due amount" boxes on enrol/renew |

## 4. Biometric attendance — ZKTeco (Sep 22)

| Requirement | Response |
|---|---|
| Face-terminal check-ins without staff | ZKTeco ADMS push endpoints; ATTLOG parser; attendance ingested against the member's device PIN (with tests) |
| Register terminals | Devices screen + device registration |
| Link a member to the terminal | Biometric enrolment on the member profile: device PIN + recorded consent |
| Handle bad/denied punches | `/attendance/unmatched` reconciliation page: assign unknown PINs to members, review rejected check-ins (e.g. no active plan) |
| Suspended gyms must not check in | Tenant suspension also blocks ADMS check-ins |

## 5. Dashboard, finance & reports (Sep 24 – Oct 9)

| Requirement | Response |
|---|---|
| Home dashboard | Profit / Income / Expense / Discount tiles; category tiles (Admission, Renewals, Due Paid, PT, Service, Product); Online vs Cash; recent transactions |
| Classify income automatically | First subscription = Admission, later ones = Renewal, balance payments = Due Payment |
| Finance report matching GymOps | `/finance` with period picker (incl. custom range), Income and Expense tabs, add income (PT/service/product), add/edit/delete expenses, paginated tables |
| Daily status report by email | Daily Active/Expired/Due Excel report, emailed (default recipient livnexacare@gmail.com) |
| Printable member directory | Member directory PDF with photos (photos downscaled to avoid timeouts/out-of-memory on the full list) |

## 6. Super-admin console — Livnexa Care (Sep 22 – Oct 3)

| Requirement | Response |
|---|---|
| Manage all gyms on the platform | `/admin` console: every tenant with plan tier, billing status, Gym Control subscription days left, usage vs limits, amount paid |
| Control a gym's access and limits | Per-tenant page: billing status/suspension, plan tier, subscription date, member/device/branch limits |
| Super-admin only | Separate super-admin auth dependency on every `/admin/*` route |

## 7. Branding, phones & reliability (Oct 2 – Oct 9)

| Requirement | Response |
|---|---|
| Gym Control look | Yellow/black theme app-wide, real logo and favicon |
| Use it like an app on a phone | Installable PWA ("Add to Home Screen") |
| Don't fail silently when logged out | Expired/stale sessions handled instead of silent 401s |
| Owner-only Dashboard/Finance/Devices | Built, then **reverted** at the owner's request (Oct 9) — not active |

## 8. Session of 12–14 Oct 2026 — requests and responses

### 8.1 Show the amount paid when viewing/editing a membership
**Asked:** Viewing or editing a membership didn't show what the member paid for their active/expired plan.
**Done (`af82f09`):** Member popup, Edit Membership and the full profile now show **"Paid ₹X"** (completed payments for that plan, plus any discount).

### 8.2 Renewal start date for expired plans
**Asked:** When renewing, default the start date to *today − days expired*.
**Done (`af82f09`):** Renewing an expired plan now defaults to the date it expired, so lapsed days aren't given free. Active plans still start from their end date; cancelled/no plan default to today. Always editable.

### 8.3 Discounted payments recorded at full price
**Asked:** A ₹15,000 yearly plan with ₹3,000 discount showed ₹15,000 received instead of ₹12,000 — finance data was wrong.
**Found:** "Amount paid" auto-filled the full plan price and didn't drop when a discount was typed, so **45 subscriptions** (43 real, 2 test) had income overstated — **₹1,23,300** in total.
**Done:**
- Form fix (`77d89f0`): amount paid follows *price − discount*; saving is blocked if amount paid exceeds the final price (add-member and renew forms).
- Data fix (approved): the 45 payment amounts were set to *price − discount*. Original rows backed up to `D:\gym\backups\payment_backup_2026-10-12_before_discount_fix.json`.
- Two members had a 100% discount (₹15,000 on a ₹15,000 plan) and now show ₹0 paid — to be confirmed with the gym.

### 8.4 Fit phones and tablets
**Asked:** Pages didn't fit the screen on mobile; make it mobile- and tablet-friendly.
**Done (`aafc336`):**
- Menu button (☰) on phones/tablets instead of 8 wrapping links; sticky top bar.
- Member popup becomes a full-width bottom sheet on phones; bigger touch targets.
- Profile header, page headers, filters and pagination wrap instead of overflowing.
- Dashboard tiles shrink so large amounts don't widen the page.
- 16px form text on phones/tablets (stops iPhone zoom-on-tap); no sideways page scrolling.

### 8.5 Cards / Table view switch on Members
**Asked:** A view toggle; cards with photo, ACTIVE/EXPIRED in bold and colour-coded, days left and plan.
**Done (`90dd74f`):** **▦ Cards / ☰ Table** switch, remembered per device (phones start on Cards). Cards show photo, name, #/phone, bold status pill (ACTIVE green, EXPIRED red, FROZEN blue, CANCELLED grey) with matching left edge, plan name, days left (amber within 7 days, red once expired), amount due, WhatsApp/view buttons. Table status badge is bold uppercase too.

### 8.6 Collect due payment in Edit Membership
**Asked:** Collect a member's due payment from Edit Membership.
**Done (`ab469e0`):** When something is due, Edit Membership shows a **Collect due payment** box (amount pre-filled with the full due, payment method). It's recorded as **Due Payment** income and lowers the amount due; overpayments are refused.

### 8.7 Back camera on mobile
**Asked:** Couldn't use the back camera to take member photos on a phone.
**Found:** The live camera always asked for the front camera, and the phone file picker was also forced to the front camera.
**Done:** Phones/tablets now open the back camera by default, with a **🔄 Front camera / Back camera** switch (shown when the device has more than one camera). "Choose file" now lets the phone pick either camera or the gallery. Only the front camera preview is mirrored.

### 8.8 Deployment note
Vercel stopped auto-deploying pushes on 12 Oct (redeploying an old deployment rebuilds the old commit, not the latest). It resumed by 13 Oct. If a push isn't picked up: Vercel → Deployments → "…" → **Create Deployment** with `main`, and check the Vercel GitHub app still has access to `gym-os`.

---

## 9. Open items

- Confirm the two 100%-discount payments (now ₹0 paid) with the gym.
- Render free tier sleeps — move to Starter before relying on live biometric pushes.
- Owner-only sections were reverted; revisit if role-based access is needed.
