/** API types (mirror backend models; money/percentages are decimal strings). */

export type Money = string;
export type MonthStr = string; // YYYY-MM

export interface Share {
  user_id: string;
  pct: Money;
}
export interface SplitRef {
  split_id: string;
}
export type Allocation = Share[] | SplitRef;

export const isSplitRef = (a: Allocation | null | undefined): a is SplitRef =>
  !!a && !Array.isArray(a) && "split_id" in a;

export interface IncomeEntry {
  from_month: MonthStr;
  amount: Money;
}
export interface IncomeSource {
  name: string;
  history: IncomeEntry[];
}
export interface OneOffIncome {
  month: MonthStr;
  amount: Money;
  description: string;
}
export interface User {
  id: string;
  name: string;
  aliases: string[];
  income_history: IncomeEntry[];
  benefit_income_history: IncomeEntry[];
  /** R14.4: named incomes (e.g. two jobs), each with its own history. */
  incomes?: IncomeSource[];
  /** R14.4: income of a single month (e.g. a bonus). */
  one_off_incomes?: OneOffIncome[];
  /** R13.11: whoever this user owes is owed to this other user instead ("Repassar o que deve para"). */
  collector_user_id?: string | null;
}
/** Work benefit (R11.5): "card" = benefit card (account type benefit); "account" = checking. */
export interface Benefit {
  id: string;
  name: string;
  user_id: string;
  destination: "card" | "account";
  account_id: string;
  amount_history: IncomeEntry[];
  active: boolean;
}
export type SplitMode = "fixed" | "income_proportional";
/** One version of a split profile. R13.12: each version has its own mode; ``shares`` is empty when
 * proportional. ``mode`` null/absent means "use the profile mode" (legacy data). */
export interface SplitVersion {
  from_month: MonthStr;
  mode?: SplitMode | null;
  shares: Share[];
}
export interface SplitProfile {
  id: string;
  name: string;
  members: string[];
  /** Legacy: default for versions without their own mode. */
  mode: SplitMode;
  history: SplitVersion[];
}
export type AccountType = "checking" | "benefit" | "cash";
export interface Account {
  id: string;
  name: string;
  type: AccountType;
  owners: Allocation;
  responsible_user_id: string;
  /** R14.1: several people paying the bank (null = only the responsible). */
  responsibles?: Allocation | null;
  profile_id: string | null;
  account_hint: string | null;
  confirm_manual_after_days: number | null;
  /** R13.17: benefit cards (VR/VA) renew on this day; no closing/due day. Only for type benefit. */
  renewal_day?: number | null;
}
export interface BillingEntry {
  from_month: MonthStr;
  closing_day: number;
  due_day: number;
}
export interface Card {
  id: string;
  name: string;
  parent_card_id: string | null;
  account_id: string | null;
  owners: Allocation | null;
  responsible_user_id: string | null;
  /** R14.1: inherited together with responsible_user_id. */
  responsibles?: Allocation | null;
  last_digits: string[];
  billing_history: BillingEntry[];
  limit: Money | null;
  profile_id: string | null;
}
export interface Category {
  id: string;
  name: string;
  color: string;
  budget: Money | null;
  /** R14.24: what goes in this category. */
  description?: string | null;
}
export interface SavingsGoal {
  id: string;
  name: string;
  monthly_amount: Money;
  user_id: string | null;
}
export type PaymentMethod =
  | "credit"
  | "benefit"
  | "debit"
  | "pix"
  | "transfer"
  | "boleto"
  | "cash";
export type Kind =
  | "expense"
  | "refund"
  | "fee"
  | "income"
  | "transfer"
  | "settlement"
  | "investment";

export interface Suggestion {
  type: string;
  target_id: string | null;
  score: Money | null;
  data: Record<string, unknown>;
  candidates: string[];
  rejected: boolean;
}
export interface ReviewInfo {
  status: "pending" | "needs_choice" | "overlap";
  suggestions: Suggestion[];
  warnings: string[];
}
export interface Transaction {
  id: string;
  /** R14.32: which benefit of a benefit card paid it. */
  benefit_id?: string | null;
  fingerprint: string | null;
  kind: Kind;
  source: {
    type: "import" | "manual";
    sha256: string | null;
    path: string | null;
    line: number | null;
  };
  provisional: boolean;
  payment_method: PaymentMethod;
  card_id: string | null;
  account_id: string | null;
  purchase_date: string;
  invoice_month: MonthStr;
  description: string;
  amount: Money;
  category_id: string | null;
  installment: { plan_id: string | null; n: number; of: number } | null;
  links: Record<string, unknown>;
  allocations: Allocation | null;
  allocation_origin: string | null;
  note: string | null;
  tag: string | null;
  review: ReviewInfo | null;
}
export interface Anticipation {
  from_n: number;
  target_month: MonthStr;
  amount: Money | null;
  linked_fingerprints: string[];
}
export interface InstallmentPlan {
  id: string;
  origin: { type: "import" | "manual"; fingerprint: string | null };
  card_id: string;
  description: string;
  total_installments: number;
  first_invoice_month: MonthStr;
  total_amount: Money;
  installment_amount: Money | null;
  category_id: string | null;
  allocations: Allocation | null;
  status_override: {
    status: "cancelled" | "anticipated_at_bank";
    from_n: number;
  } | null;
  anticipation: Anticipation | null;
  warnings: string[];
}
export interface Subscription {
  id: string;
  description: string;
  amount: Money;
  period: "monthly" | "annual";
  month_of_year: number | null;
  payment_method: PaymentMethod;
  card_id: string | null;
  account_id: string | null;
  start_month: MonthStr;
  end_month: MonthStr | null;
  category_id: string | null;
  allocations: Allocation | null;
  /** R14.9: reajustes from a month on. */
  price_history?: { from_month: MonthStr; amount: Money }[];
  /** R14.11: months it was off (until null = still off). */
  pauses?: { from_month: MonthStr; until_month: MonthStr | null }[];
  /** R14.27: the split from a month on (null = back to "Padrão"). */
  allocation_history?: {
    from_month: MonthStr;
    allocations: Allocation | null;
  }[];
  /** R14.32: which benefit of the benefit card pays it. */
  benefit_id?: string | null;
  /** R14.26: "household" = conta da casa (luz, água, aluguel…). */
  group?: "subscription" | "household";
  due_day?: number | null;
}
export interface RecurringPurchase {
  id: string;
  description: string;
  match_description: string | null;
  estimated_amount: Money;
  every: { value: number; unit: "days" | "weeks" | "months" };
  last_date: string;
  payment_method: PaymentMethod;
  card_id: string | null;
  account_id: string | null;
  category_id: string | null;
  allocations: Allocation | null;
  active: boolean;
  skipped_dates: string[];
  next_date: string | null;
  /** R14.9: estimated price from a month on (month of the purchase). */
  price_history?: { from_month: MonthStr; amount: Money }[];
  /** R14.11: months it was off (until null = still off). */
  pauses?: { from_month: MonthStr; until_month: MonthStr | null }[];
  /** R14.27: the split from a month on (null = back to "Padrão"). */
  allocation_history?: {
    from_month: MonthStr;
    allocations: Allocation | null;
  }[];
  /** R14.26: "household" = conta da casa (occurrence date = due date). */
  group?: "purchase" | "household";
  /** R14.32: which benefit of the benefit card pays it. */
  benefit_id?: string | null;
  /** R14.30: "todo dia X do mês" (monthly interval only). */
  day_of_month?: number | null;
}
export interface Rule {
  id: string;
  priority: number;
  enabled: boolean;
  when: {
    description_regex: string | null;
    card_id: string | null;
    account_id: string | null;
    category_id: string | null;
    min_amount: Money | null;
    max_amount: Money | null;
  };
  then: { category_id: string | null; allocations: Allocation | null };
}
export interface Settlement {
  id: string;
  origin: { type: "import" | "manual"; fingerprint: string | null };
  from_user_id: string;
  to_user_id: string;
  amount: Money;
  date: string;
  month: MonthStr;
  note: string | null;
  warnings: string[];
  /** R13.16: receivable this settlement pays off (set by mark-received; null for free settlements). */
  card_id?: string | null;
  account_id?: string | null;
  invoice_month?: MonthStr | null;
}
/** R13.15: non-bank place where investments live (broker, exchange, pension fund...). */
export type InstitutionType =
  | "broker"
  | "exchange"
  | "pension"
  | "bank"
  | "other";
export interface Institution {
  id: string;
  name: string;
  type: InstitutionType;
}
export interface Investment {
  id: string;
  name: string;
  /** Legacy free text; new investments use ``institution_id``. */
  institution: string | null;
  /** R13.15: id of an account or of an institution. */
  institution_id?: string | null;
  type:
    | "emergency_reserve"
    | "fixed_income"
    | "stocks"
    | "funds"
    | "pension"
    | "crypto"
    | "other";
  owners: Allocation;
  goal_id: string | null;
  account_id: string | null;
  snapshots: { date: string; balance: Money }[];
  movements: {
    date: string;
    type: "contribution" | "withdrawal";
    amount: Money;
    warnings: string[];
  }[];
  closed_at: string | null;
}
export interface ManifestEntry {
  path: string;
  sha256: string;
  kind: "fatura" | "extrato";
  format: "pdf" | "csv";
  profile_id: string | null;
  card_id: string | null;
  account_id: string | null;
  invoice_month: MonthStr | null;
  total: Money | null;
  amount_due: Money | null;
  open_invoice: boolean;
  status: string;
  label?: string;
  error: string | null;
  warnings: string[];
  supersedes_candidate: string | null;
  superseded_by: string | null;
  duplicate_of: string | null;
  paid_by_fingerprints: string[];
}
export interface Alert {
  type:
    | "uncategorized"
    | "recurring_overdue"
    | "missing_invoice"
    | "files_need_attention"
    | "inconsistent_files";
  count?: number;
  items?: Record<string, string[]>;
  recurring_id?: string;
  description?: string;
  planned_date?: string;
  card_id?: string;
  month?: string;
  paths?: string[];
}
export interface MonthSeries {
  month: MonthStr;
  total: Money;
  income?: Money | null;
  benefit_income?: Money | null;
  by_card: Record<string, Money>;
  by_method: Record<string, Money>;
  by_category?: Record<string, Money>;
  states: Record<string, "real" | "open" | "projected" | "missing">;
}
export interface Summary {
  month: MonthStr;
  total: Money;
  by_category: Record<string, Money>;
  uncategorized_key: string;
  by_card: Record<string, Money>;
  by_method: Record<string, Money>;
  states: Record<string, string>;
  series: MonthSeries[];
  annual: Record<MonthStr, Record<string, Money>>;
  /** R14.36: per month, spending per card/account (benefit cards included). */
  annual_by_card?: Record<MonthStr, Record<string, Money>>;
  /** R14.36: per month, how much of it was paid with benefit. */
  annual_benefit?: Record<MonthStr, Money>;
  goals: Record<string, { target: Money; achieved: Money }>;
}
export interface Commitment {
  month: MonthStr;
  spent: Money;
  income: Money | null;
  ratio: Money | null;
  band: "green" | "yellow" | "red" | null;
  benefit_spent: Money;
  benefit_income: Money | null;
  benefit_ratio: Money | null;
}
export interface Projection {
  months: MonthSeries[];
  committed_income: { user_id: string; months: Commitment[] }[];
  /** R14.33: every person (income may be null), for "Gasto por pessoa". */
  people?: { user_id: string; months: Commitment[] }[];
}
export interface Balances {
  user_id: string;
  incomplete_months: MonthStr[];
  people: {
    user_id: string;
    net: Money;
    months: {
      month: MonthStr;
      net: Money;
      incomplete: boolean;
      lines: { ref_id: string; description: string; amount: Money }[];
      settlements: Settlement[];
    }[];
  }[];
}
export interface InvestmentsReport {
  total: Money;
  yield_total: Money;
  by_type: Record<string, Money>;
  by_user: Record<string, Money>;
  positions: {
    investment_id: string;
    balance: Money;
    balance_date: string | null;
    net_contributions: Money;
    yield: Money | null;
    stale: boolean;
    estimated: boolean;
  }[];
  evolution: { month: MonthStr; balance: Money; contributions: Money }[];
}
export interface ReviewFile {
  file: ManifestEntry;
  label: string;
  count: number;
  lines: Transaction[];
}

/** R13.11: one receivable/payable per card/account and invoice month (GET /api/reports/receivables). */
export interface ReceivableItem {
  counterparty_user_id: string;
  /** "receive": the counterparty owes the user; "pay": the user owes the counterparty. */
  direction: "receive" | "pay";
  card_id: string | null;
  account_id: string | null;
  invoice_month: MonthStr;
  /** Due date of the invoice where the purchase was made (deadline); null when unknown. */
  due_date: string | null;
  amount: Money;
  overdue: boolean;
  settled_month_total: Money;
  /** R13.16: part of ``amount`` already paid off by settlements linked to this card/account and month. */
  settled: Money;
  /** ``amount`` - ``settled`` (never negative). */
  remaining: Money;
  status: "open" | "partial" | "received";
}
/** R14.15: what people are expected to owe from forecasts (not settled, not in totals). */
export interface ForecastReceivable {
  counterparty_user_id: string;
  direction: "receive" | "pay";
  card_id: string | null;
  account_id: string | null;
  invoice_month: MonthStr;
  due_date: string | null;
  amount: Money;
}
export interface Receivables {
  user_id: string;
  items: ReceivableItem[];
  forecast?: {
    items: ForecastReceivable[];
    totals: { receive: Money; pay: Money };
  };
  /** Sum of ``remaining`` per direction. */
  totals: { receive: Money; pay: Money };
}
/** Body of POST /api/reports/receivables/mark-received (R13.16). */
export interface MarkReceivedBody {
  user_id: string;
  counterparty_user_id: string;
  direction: ReceivableItem["direction"];
  card_id: string | null;
  account_id: string | null;
  invoice_month: MonthStr;
  /** Omitted: settle everything that remains. */
  amount?: Money;
}
