export type Field = {
  name: string;
  html_name: string;
  label: string;
  kind: string;
  value: any;
  required: boolean;
  disabled: boolean;
  help: string;
  choices: { value: string; label: string }[];
  errors: string[];
  max_length?: number;
  min?: string;
  max?: string;
  placeholder?: string;
  localized?: boolean;
  split: boolean;
};
export type FormRow = {
  fields: Field[];
  readonly: { name: string; label: string; value: any }[];
  errors: string[];
};
