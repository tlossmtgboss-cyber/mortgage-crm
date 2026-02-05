/**
 * Common utility types used throughout the application
 */

// ============================================================================
// UTILITY TYPES
// ============================================================================

/**
 * Makes all properties of T optional and nullable
 */
export type DeepPartial<T> = {
  [P in keyof T]?: T[P] extends object ? DeepPartial<T[P]> : T[P] | null;
};

/**
 * Extracts the type of array elements
 */
export type ArrayElement<T> = T extends readonly (infer U)[] ? U : never;

/**
 * Makes specified keys required while keeping others optional
 */
export type RequireKeys<T, K extends keyof T> = Omit<T, K> & Required<Pick<T, K>>;

/**
 * Makes specified keys optional while keeping others required
 */
export type OptionalKeys<T, K extends keyof T> = Omit<T, K> & Partial<Pick<T, K>>;

/**
 * Excludes null and undefined from T
 */
export type NonNullable<T> = T extends null | undefined ? never : T;

/**
 * Creates a type from the values of an object
 */
export type ValueOf<T> = T[keyof T];

// ============================================================================
// FORM & INPUT TYPES
// ============================================================================

/**
 * Generic form field state
 */
export interface FormFieldState<T = string> {
  value: T;
  error: string | null;
  touched: boolean;
  dirty: boolean;
}

/**
 * Form submission state
 */
export interface FormState {
  isSubmitting: boolean;
  isValid: boolean;
  isDirty: boolean;
  errors: Record<string, string>;
}

/**
 * Select option type for dropdowns
 */
export interface SelectOption<T = string> {
  value: T;
  label: string;
  disabled?: boolean;
  group?: string;
}

/**
 * Date range for filtering
 */
export interface DateRange {
  start: Date | null;
  end: Date | null;
}

/**
 * Sort configuration
 */
export interface SortConfig {
  field: string;
  direction: 'asc' | 'desc';
}

/**
 * Pagination configuration
 */
export interface PaginationConfig {
  page: number;
  pageSize: number;
  total?: number;
}

// ============================================================================
// UI STATE TYPES
// ============================================================================

/**
 * Loading state with optional error
 */
export interface LoadingState {
  isLoading: boolean;
  error: string | null;
}

/**
 * Async operation state
 */
export interface AsyncState<T> {
  data: T | null;
  isLoading: boolean;
  error: string | null;
  isSuccess: boolean;
}

/**
 * Modal state
 */
export interface ModalState {
  isOpen: boolean;
  data?: unknown;
}

/**
 * Toast/notification message
 */
export interface ToastMessage {
  id: string;
  type: 'success' | 'error' | 'warning' | 'info';
  message: string;
  title?: string;
  duration?: number;
  dismissible?: boolean;
}

/**
 * Confirmation dialog state
 */
export interface ConfirmationState {
  isOpen: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: 'danger' | 'warning' | 'info';
  onConfirm: () => void | Promise<void>;
  onCancel?: () => void;
}

// ============================================================================
// TABLE & LIST TYPES
// ============================================================================

/**
 * Table column definition
 */
export interface TableColumn<T> {
  key: keyof T | string;
  header: string;
  sortable?: boolean;
  width?: string | number;
  align?: 'left' | 'center' | 'right';
  render?: (value: unknown, row: T) => React.ReactNode;
}

/**
 * Row selection state
 */
export interface SelectionState<T = number> {
  selectedIds: Set<T>;
  isAllSelected: boolean;
  isIndeterminate: boolean;
}

/**
 * Filter configuration for tables
 */
export interface TableFilter {
  field: string;
  operator: 'eq' | 'ne' | 'gt' | 'gte' | 'lt' | 'lte' | 'contains' | 'in';
  value: unknown;
}

// ============================================================================
// EVENT HANDLER TYPES
// ============================================================================

/**
 * Generic change handler
 */
export type ChangeHandler<T = string> = (value: T) => void;

/**
 * Generic submit handler
 */
export type SubmitHandler<T> = (data: T) => void | Promise<void>;

/**
 * Click handler with optional event
 */
export type ClickHandler<T = void> = (
  event: React.MouseEvent<HTMLElement>,
  data?: T
) => void;

// ============================================================================
// ROUTE & NAVIGATION TYPES
// ============================================================================

/**
 * Breadcrumb item
 */
export interface BreadcrumbItem {
  label: string;
  path?: string;
  icon?: React.ReactNode;
}

/**
 * Navigation item
 */
export interface NavItem {
  id: string;
  label: string;
  path: string;
  icon?: React.ReactNode;
  badge?: string | number;
  children?: NavItem[];
  permissions?: string[];
}

// ============================================================================
// MISC TYPES
// ============================================================================

/**
 * Key-value record for generic objects
 */
export type GenericRecord = Record<string, unknown>;

/**
 * Nullable type helper
 */
export type Nullable<T> = T | null;

/**
 * Optional type helper
 */
export type Optional<T> = T | undefined;

/**
 * ID type (can be number or string depending on backend)
 */
export type EntityId = number | string;

/**
 * Timestamp string in ISO format
 */
export type ISODateString = string;

/**
 * Currency amount (stored as number, formatted for display)
 */
export type CurrencyAmount = number;

/**
 * Percentage value (0-100)
 */
export type Percentage = number;

/**
 * Phone number string
 */
export type PhoneNumber = string;

/**
 * Email address string
 */
export type EmailAddress = string;
