// Shapes returned by `python -m finance serve`. Money arrives as JSON numbers rounded to cents.

export type Kind = "income" | "expense" | "refund" | "internal_transfer" | "unmatched_transfer";

export interface Account {
  id: string;
  type: string;
  name: string;
}

export interface Meta {
  accounts: Account[];
  categories: string[];
  first_date: string;
  last_date: string;
}

export interface CashFlow {
  income: number;
  gross_spend: number;
  refunds: number;
  expenses: number;
  net_cash_flow: number;
  savings_rate: number | null;
  internal_transfers_excluded: number;
  unmatched_transfers_excluded: number;
  transaction_count: number;
}

export interface MerchantSpend {
  merchant: string;
  total: number;
  purchases: number;
  refunds: number;
}

export interface MonthSummary extends CashFlow {
  month: string;
  spending_by_category: Record<string, number>;
  top_merchants: MerchantSpend[];
  rolling_30_day_daily_average_at_month_end: number | null;
}

export interface PriceChange {
  date: string;
  from: number;
  to: number;
}

export interface RecurringCharge {
  merchant: string;
  category: string;
  cadence: string;
  current_amount: number;
  occurrences: number;
  first_date: string;
  last_date: string;
  next_expected: string;
  annualized_cost: number;
  accounts: string[];
  active: boolean;
  price_changes: PriceChange[];
}

export interface DuplicateGroup {
  account_id: string;
  merchant: string;
  amount: number;
  dates: string[];
  ids: string[];
  suggested_keep: string;
}

export interface Transaction {
  id: string;
  account_id: string;
  date: string;
  merchant: string;
  amount: number;
  type: string;
  category: string | null;
  effective_category: string;
  category_inferred: boolean;
  kind: Kind;
  transfer_group: string | null;
  probable_duplicate?: boolean;
}

export interface ValidationIssue {
  index: number;
  id: string | null;
  field: string | null;
  message: string;
}

export interface DataQuality {
  total_records: number;
  valid_transactions: number;
  rejected_records: number;
  exact_duplicates_removed: number;
  categories_inferred: number;
  uncategorized: number;
  internal_transfer_pairs: number;
  internal_transfer_pairs_by_method: Record<string, number>;
  unmatched_transfers: Transaction[];
  issues: ValidationIssue[];
}

export interface Summary {
  totals: CashFlow & {
    spending_by_category: Record<string, number>;
    top_merchants: MerchantSpend[];
  };
  months: MonthSummary[];
  recurring_charges: RecurringCharge[];
  probable_duplicates: DuplicateGroup[];
  data_quality: DataQuality;
}

export interface RollingPoint {
  date: string;
  window_total: number;
  daily_average: number;
  complete_window: boolean;
}

export interface Rolling {
  window_days: number;
  points: RollingPoint[];
}

export interface TransactionPage {
  total: number;
  offset: number;
  limit: number;
  items: Transaction[];
}

export interface Filters {
  start: string | null;
  end: string | null;
  accounts: string[];
  category: string | null;
  merchant: string;
  dropDuplicates: boolean;
}
