/**
 * Zod schemas for URLA section validation.
 *
 * The backend stores section data as a JSONB blob and does not enforce
 * field-level shape — that's intentional, so the URLA can evolve without
 * server migrations. Validation lives here on the client (and again at
 * submit time in the canonical-store handler in your existing codebase).
 *
 * Each schema is `.partial()` because autosave fires on every keystroke;
 * we only run the strict version (`.parse(...)`) when the borrower clicks
 * "Save & Continue".
 */
import { z } from 'zod';

import type { SectionKey } from '../types';

// ---------- shared primitives ----------

const usState = z
  .string()
  .length(2, 'Use the 2-letter state code (e.g. CA)')
  .regex(/^[A-Z]{2}$/);

const zipCode = z.string().regex(/^\d{5}(-\d{4})?$/, 'ZIP must be 5 or 9 digits');

const phone = z
  .string()
  .regex(/^[\d\s().+-]{7,20}$/, 'Enter a valid phone number');

const email = z.string().email('Enter a valid email');

const currency = z
  .number({ error: 'Enter a number' })
  .nonnegative('Cannot be negative');

// ---------- section schemas ----------

export const personalSchema = z.object({
  first_name: z.string().min(1, 'Required'),
  middle_name: z.string().optional(),
  last_name: z.string().min(1, 'Required'),
  suffix: z.string().optional(),
  email,
  phone,
  marital_status: z.enum(['married', 'single', 'separated', 'unmarried']),
  dependents_count: z.number().int().nonnegative().optional(),
});

const addressSchema = z.object({
  street: z.string().min(1),
  unit: z.string().optional(),
  city: z.string().min(1),
  state: usState,
  zip: zipCode,
  housing_status: z.enum(['own', 'rent', 'no_charge']),
  years_at_address: z.number().int().nonnegative(),
  months_at_address: z.number().int().nonnegative().optional(),
  monthly_cost: currency,
});

export const residenceSchema = z.object({
  current: addressSchema,
  previous: addressSchema.partial().optional(),
});

export const employmentSchema = z.object({
  employment_type: z.enum([
    'employee', 'self_employed', 'contractor', 'retired', 'military', 'other',
  ]),
  years_in_profession: z.number().int().nonnegative().optional(),
  employer: z.object({
    name: z.string().min(1),
    position: z.string().min(1),
    start_date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
    phone: phone.optional(),
    is_self_employed: z.boolean().optional(),
    street: z.string().optional(),
    city: z.string().optional(),
    state: usState.optional(),
    zip: zipCode.optional(),
  }),
  income: z.object({
    base: currency,
    overtime: currency.optional(),
    bonus: currency.optional(),
    commission: currency.optional(),
    other: currency.optional(),
  }),
});

export const assetsSchema = z.object({
  accounts: z
    .array(
      z.object({
        type: z.enum([
          'checking', 'savings', 'money_market', 'cd',
          'retirement_401k', 'retirement_ira', 'brokerage', 'gift',
        ]),
        institution: z.string().min(1),
        account_number_last4: z.string().regex(/^\d{4}$/).optional(),
        balance: currency,
      }),
    )
    .min(1, 'Add at least one account'),
  receiving_gift: z.boolean(),
  gift_amount: currency.optional(),
  gift_donor: z.string().optional(),
  gift_relationship: z.string().optional(),
});

export const liabilitiesSchema = z.object({
  liabilities: z.array(
    z.object({
      type: z.string().min(1),
      creditor: z.string().min(1),
      balance: currency.optional(),
      monthly_payment: currency,
      pay_off_at_close: z.boolean().optional(),
    }),
  ),
});

export const reoSchema = z.object({
  owns_other_property: z.boolean(),
  properties: z
    .array(
      z.object({
        address: z.string().min(1),
        property_type: z.string().min(1),
        market_value: currency.optional(),
        monthly_payment: currency.optional(),
        monthly_rental_income: currency.optional(),
        status: z.enum(['retain', 'sell_pending', 'sold']),
      }),
    )
    .optional(),
});

export const loanSchema = z.object({
  loan_purpose: z.enum(['purchase', 'refinance', 'cash_out_refi', 'construction']),
  loan_type: z.enum(['conventional', 'fha', 'va', 'usda', 'jumbo']),
  loan_amount: currency,
  property: z.object({
    address: z.string().min(1),
    type: z.string().min(1),
    occupancy: z.enum(['primary', 'second_home', 'investment']),
    value: currency,
    year_built: z.number().int().optional(),
  }),
});

export const declarationsSchema = z.object({
  will_occupy_as_primary: z.boolean(),
  has_recent_ownership: z.boolean(),
  other_mortgage_on_property: z.boolean(),
  borrowed_down_payment: z.boolean(),
  cosigner_on_other_loans: z.boolean(),
  outstanding_judgments: z.boolean(),
  bankruptcy_7_years: z.boolean(),
  foreclosure_7_years: z.boolean(),
  party_to_lawsuit: z.boolean(),
  federal_debt_delinquent: z.boolean(),
  us_citizen: z.boolean(),
  permanent_resident: z.boolean(),
});

export const SECTION_SCHEMAS: Record<SectionKey, z.ZodTypeAny> = {
  personal: personalSchema,
  coborrower: z.object({}).passthrough(),
  residence: residenceSchema,
  employment: employmentSchema,
  assets: assetsSchema,
  liabilities: liabilitiesSchema,
  reo: reoSchema,
  loan: loanSchema,
  documents_upload: z.object({}).passthrough(),
  declarations: declarationsSchema,
  credit_auth: z.object({}).passthrough(),
  schedule: z.object({}).passthrough(),
  review: z.object({}).passthrough(),
};

/**
 * Validate a section, returning either the parsed data or an array of
 * field-path issues for inline display.
 */
export function validateSection(key: SectionKey, data: unknown):
  | { ok: true; data: unknown }
  | { ok: false; issues: { path: string; message: string }[] } {
  const schema = SECTION_SCHEMAS[key];
  const result = schema.safeParse(data);
  if (result.success) return { ok: true, data: result.data };
  return {
    ok: false,
    issues: result.error.issues.map(i => ({
      path: i.path.join('.'),
      message: i.message,
    })),
  };
}
