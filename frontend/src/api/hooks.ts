/** TanStack Query hooks over the REST API. */
import {
  useMutation,
  useQuery,
  useQueryClient,
  type QueryKey,
} from "@tanstack/react-query";
import { api } from "./client";
import { ownerLabels } from "../lib/ownerLabel";
import type {
  Account,
  Alert,
  Benefit,
  Card,
  Category,
  InstallmentPlan,
  Institution,
  Investment,
  RecurringPurchase,
  Rule,
  SavingsGoal,
  Settlement,
  SplitProfile,
  Subscription,
  User,
} from "./types";

export interface ResourceMap {
  users: User;
  "split-profiles": SplitProfile;
  accounts: Account;
  cards: Card;
  categories: Category;
  "savings-goals": SavingsGoal;
  subscriptions: Subscription;
  "recurring-purchases": RecurringPurchase;
  "installment-plans": InstallmentPlan;
  rules: Rule;
  settlements: Settlement;
  investments: Investment;
  benefits: Benefit;
  institutions: Institution;
}
export type Resource = keyof ResourceMap;

/** Every mutation invalidates everything: data is small and panels depend on each other. */
function useInvalidateAll() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries();
}

export function useList<R extends Resource>(resource: R) {
  return useQuery({
    queryKey: [resource],
    queryFn: () => api.get<ResourceMap[R][]>(`/api/${resource}`),
  });
}

export function useSave<R extends Resource>(resource: R) {
  const invalidate = useInvalidateAll();
  return useMutation({
    mutationFn: (item: Partial<ResourceMap[R]> & { id?: string }) =>
      item.id
        ? api.put<ResourceMap[R]>(
            `/api/${resource}/${encodeURIComponent(item.id)}`,
            item,
          )
        : api.post<ResourceMap[R]>(`/api/${resource}`, item),
    onSuccess: invalidate,
  });
}

export function useRemove<R extends Resource>(resource: R) {
  const invalidate = useInvalidateAll();
  return useMutation({
    mutationFn: (id: string) =>
      api.del<{ deleted: string; uncategorized?: Record<string, number> }>(
        `/api/${resource}/${encodeURIComponent(id)}`,
      ),
    onSuccess: invalidate,
  });
}

export function useGet<T>(
  key: QueryKey,
  path: string | null,
  refetchInterval?: number,
) {
  return useQuery({
    queryKey: key,
    queryFn: () => api.get<T>(path as string),
    enabled: path !== null,
    refetchInterval,
  });
}

/** Generic mutation that refreshes all queries afterwards. */
export function useAction<TBody, TResult = unknown>(
  method: "post" | "put" | "patch" | "del",
  path: (body: TBody) => string,
  body?: (input: TBody) => unknown,
) {
  const invalidate = useInvalidateAll();
  return useMutation({
    mutationFn: (input: TBody) => {
      const url = path(input);
      const payload = body ? body(input) : input;
      if (method === "del") return api.del<TResult>(url);
      return api[method]<TResult>(url, payload);
    },
    onSuccess: invalidate,
  });
}

export function useAlerts() {
  return useQuery({
    queryKey: ["alerts"],
    queryFn: () => api.get<Alert[]>("/api/alerts"),
  });
}

/** R14.3: id -> unambiguous card/account label (see lib/ownerLabel). */
export function useOwnerLabels(): Record<string, string> {
  const cards = useList("cards");
  const accounts = useList("accounts");
  return ownerLabels(cards.data ?? [], accounts.data ?? []);
}

/** id -> name lookup helpers for selects and labels. */
export function useNames() {
  const users = useList("users");
  const cards = useList("cards");
  const accounts = useList("accounts");
  const categories = useList("categories");
  const splits = useList("split-profiles");
  const map = <T extends { id: string; name: string }>(rows: T[] | undefined) =>
    Object.fromEntries((rows ?? []).map((r) => [r.id, r.name])) as Record<
      string,
      string
    >;
  // R14.3: cards and accounts that share a name get a distinguishing suffix everywhere.
  const owners = ownerLabels(cards.data ?? [], accounts.data ?? []);
  const pick = (rows: { id: string }[] | undefined) =>
    Object.fromEntries(
      (rows ?? []).map((r) => [r.id, owners[r.id] ?? r.id]),
    ) as Record<string, string>;
  return {
    users: map(users.data),
    cards: pick(cards.data),
    accounts: pick(accounts.data),
    categories: map(categories.data),
    splits: map(splits.data),
    owner: (id: string | null | undefined) => (id ? (owners[id] ?? id) : ""),
    loading:
      users.isLoading ||
      cards.isLoading ||
      accounts.isLoading ||
      categories.isLoading,
  };
}
