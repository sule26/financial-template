/** Shapes of the /api/profiles endpoints (R4.3, R13.9). */

export interface ProfileInfo {
  id: string;
  name: string;
  kind: string;
  format: string;
  file: string | null;
  files: number;
  errors: number;
}

/** Built-in example: just the id in older backends, or the same summary as a profile. */
export type ExampleInfo = string | (Partial<ProfileInfo> & { id: string });

export interface ProfilesList {
  profiles: ProfileInfo[];
  plugins: { id: string; kind: string; file: string | null }[];
  errors: Record<string, string>;
  examples: ExampleInfo[];
}

export interface ProfileTestResult {
  valid: boolean;
  error?: string | null;
  status?: string;
  detected?: boolean;
  header?: Record<string, unknown> | null;
  lines?: {
    index: number;
    date: string;
    description: string;
    amount: string;
    installment_n: number | null;
    installment_of: number | null;
    card_hint: string | null;
    kind: string | null;
  }[];
  ignored?: string[];
  unrecognized?: string[];
}
