import type { Field } from "../types/forms";

// Signals DOM changes made by composite fields, after their hidden inputs update.
export const FORM_VALUE_CHANGE = "vdd:form-value-change";
export function notifyFormChange(element: HTMLElement | null) {
  element?.dispatchEvent(new Event(FORM_VALUE_CHANGE, { bubbles: true }));
}

/** Comparison only. The FormData sent to the backend is never normalized here. */
export function formFingerprint(form: HTMLFormElement, fields: Field[]): string {
  const unordered = new Set(fields.filter(field =>
    field.kind === "multiple" || field.kind === "checkboxes" ||
    (field.kind === "relationship" && field.multiple)).map(field => field.html_name));
  const entries = new Map<string, string[]>();
  for (const [name, value] of new FormData(form)) {
    const normalized = typeof value === "string" ? value :
      !value.name && value.size === 0 ? null : [value.name, value.size, value.lastModified];
    const values = entries.get(name) || [];
    values.push(JSON.stringify(normalized));
    entries.set(name, values);
  }
  return JSON.stringify([...entries].sort(([a], [b]) => a.localeCompare(b)).map(([name, values]) =>
    [name, unordered.has(name) ? [...values].sort() : values]));
}
