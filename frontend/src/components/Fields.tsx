import { RelationshipInput } from "./RelationshipInput";
import { useState } from "react";
import {
  formatWhatsapp,
  formatPhone,
  formatDocument,
  normalizeTime,
} from "../utils/masks";
import type { Field, FormRow } from "../types/forms";
import { request } from "../api/client";
import { formatDateBR } from "../utils/dates";
export function Display({ value }: { value: any }) {
  if (value && Array.isArray(value.links))
    return (
      <>
        {value.text && <span>{value.text} </span>}
        {value.links.map((link: any) => (
          <span key={link.url}>
            <a href={link.url}>{link.label}</a>
            {" · "}
          </span>
        ))}
      </>
    );
  if (value && typeof value === "object" && value.image)
    return <img className="thumbnail" src={value.image} alt={value.label} />;
  if (value && typeof value === "object" && value.url)
    return (
      <a href={value.url} target="_blank" rel="noopener noreferrer">
        {value.label || "Ver arquivo"}
      </a>
    );
  if (typeof value === "boolean") return <>{value ? "Sim" : "Não"}</>;
  if (typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value))
    return <>{formatDateBR(value)}</>;
  return <>{String(value ?? "—") || "—"}</>;
}
export function FieldInput({ field: f }: { field: Field }) {
  const [lookup, setLookup] = useState("");
  const shared = {
    name: f.html_name,
    id: f.html_name,
    required: f.required,
    disabled: f.disabled,
    "aria-invalid": f.errors.length > 0,
    "aria-describedby": f.html_name + "-help",
  };
  const current = f.value ?? "";
  async function cep(e: React.FocusEvent<HTMLInputElement>) {
    const el = e.currentTarget,
      form = el.form,
      raw = el.value.replace(/\D/g, "");
    if (raw.length !== 8 || !form) return;
    setLookup("Consultando CEP…");
    try {
      const data = await request("/api/cep/" + raw + "/");
      if (data.success === false) throw new Error(data.error);
      const prefix = f.html_name.slice(0, -f.name.length);
      const mapping =
        f.name === "pickup_zip_code"
          ? {
              pickup_address: "street",
              pickup_neighborhood: "neighborhood",
              pickup_city: "city",
              pickup_complement: "complement",
            }
          : {
              address: "street",
              province: "neighborhood",
              complement: "complement",
            };
      for (const [target, source] of Object.entries(mapping)) {
        const input = form.elements.namedItem(
          prefix + target,
        ) as HTMLInputElement | null;
        if (
          input &&
          data[source] &&
          (!target.includes("complement") || !input.value)
        ) {
          input.value = data[source];
          input.dispatchEvent(new Event("input", { bubbles: true }));
        }
      }
      setLookup("CEP encontrado. Confira o endereço e informe o número.");
    } catch (e) {
      setLookup(
        e instanceof Error ? e.message : "Não foi possível consultar o CEP.",
      );
    }
  }
  function blur(e: React.FocusEvent<HTMLInputElement>) {
    const el = e.currentTarget;
    if (["whatsapp_number", "whatsapp_order_number"].includes(f.name))
      el.value = formatWhatsapp(el.value);
    if (["mobile_phone", "phone"].includes(f.name))
      el.value = formatPhone(el.value);
    if (f.name === "document") el.value = formatDocument(el.value);
    if (f.kind === "time") el.value = normalizeTime(el.value);
    if (["postal_code", "pickup_zip_code"].includes(f.name)) {
      el.value = el.value
        .replace(/\D/g, "")
        .slice(0, 8)
        .replace(/(\d{5})(\d)/, "$1-$2");
      void cep(e);
    }
    if (f.kind === "decimal" && !f.localized)
      el.value = el.value.replace(",", ".");
  }
  function nameChanged(e: React.ChangeEvent<HTMLInputElement>) {
    if (f.name !== "name") return;
    const form = e.currentTarget.form,
      prefix = f.html_name.slice(0, -f.name.length);
    const slug = form?.elements.namedItem(
      prefix + "slug",
    ) as HTMLInputElement | null;
    if (slug && (!slug.value || slug.dataset.auto === "true")) {
      slug.value = e.currentTarget.value
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "")
        .toLowerCase()
        .replace(/[^a-z0-9\s-]/g, "")
        .trim()
        .replace(/[\s-]+/g, "-");
      slug.dataset.auto = "true";
    }
  }
  let input;
  if (f.kind === "hidden")
    return (
      <input type="hidden" name={f.html_name} defaultValue={String(current)} />
    );
  if (f.kind === "relationship") input = <RelationshipInput field={f} />;
  else if (f.kind === "checkboxes")
    input = (
      <div>
        {f.choices.map((c) => (
          <label key={c.value}>
            <input
              type="checkbox"
              name={f.html_name}
              value={c.value}
              disabled={f.disabled}
              defaultChecked={
                Array.isArray(current) && current.map(String).includes(c.value)
              }
            />
            {c.label}
          </label>
        ))}
      </div>
    );
  else if (f.kind === "checkbox")
    input = <input {...shared} type="checkbox" defaultChecked={!!current} />;
  else if (f.kind === "file")
    input = (
      <>
        <input
          {...shared}
          required={f.required && !current?.url}
          type="file"
          accept={f.accept || undefined}
        />
        {current?.url && (
          <>
            <a href={current.url} target="_blank" rel="noopener noreferrer">
              Arquivo atual
            </a>
            {!f.required && (
              <label>
                <input type="checkbox" name={f.html_name + "-clear"} /> Remover
                arquivo
              </label>
            )}
          </>
        )}
      </>
    );
  else if (f.kind === "select" || f.kind === "multiple")
    input = (
      <select
        {...shared}
        multiple={f.kind === "multiple"}
        defaultValue={
          f.kind === "multiple"
            ? Array.isArray(current)
              ? current.map(String)
              : []
            : String(current)
        }
      >
        {f.choices.map((c) => (
          <option key={c.value} value={c.value}>
            {c.label}
          </option>
        ))}
      </select>
    );
  else if (f.kind === "textarea")
    input = (
      <textarea
        {...shared}
        defaultValue={
          typeof current === "object"
            ? JSON.stringify(current)
            : String(current)
        }
        rows={4}
      />
    );
  else
    input = (
      <input
        {...shared}
        type={["decimal", "time"].includes(f.kind) ? "text" : f.kind}
        inputMode={f.kind === "decimal" ? "decimal" : undefined}
        defaultValue={String(current)}
        maxLength={f.max_length || undefined}
        min={f.min || undefined}
        max={f.max || undefined}
        placeholder={f.placeholder}
        onBlur={blur}
        onChange={nameChanged}
        onInput={
          f.name === "slug"
            ? (e) => {
                e.currentTarget.dataset.auto = "false";
              }
            : undefined
        }
      />
    );
  return (
    <div className={"field " + (f.kind === "checkbox" ? "check-field" : "")}>
      <label htmlFor={f.html_name}>
        {f.label}
        {f.required ? " *" : ""}
      </label>
      {input}
      <small id={f.html_name + "-help"}>{f.help}</small>
      {lookup && <small role="status">{lookup}</small>}
      {f.errors.map((e, i) => (
        <p className="field-error" role="alert" key={i}>
          {e}
        </p>
      ))}
    </div>
  );
}
export function FormFields({ row }: { row: FormRow }) {
  const [values, setValues] = useState<Record<string, any>>(() =>
    Object.fromEntries(row.fields.map((f) => [f.name, f.value])),
  );
  const payment = row.fields.some((f) => f.name === "terms_accepted");
  const document = String(values.document || "").replace(/[^a-zA-Z0-9]/g, "");
  function visible(f: Field) {
    if (
      payment &&
      !values.enabled &&
      !["enabled", "id", "DELETE"].includes(f.name)
    )
      return false;
    if (payment && f.name === "birth_date" && document.length === 14)
      return false;
    if (payment && f.name === "company_type" && /^\d{11}$/.test(document))
      return false;
    if (
      row.fields.some((x) => x.name === "is_closed") &&
      values.is_closed &&
      ["opens_at", "closes_at", "opening_time", "closing_time"].includes(f.name)
    )
      return false;
    return true;
  }
  return (
    <>
      <div
        className="form-grid"
        onChange={(e) => {
          const target = e.target as HTMLInputElement;
          const field = row.fields.find((f) => f.html_name === target.name);
          if (field)
            setValues((v) => ({
              ...v,
              [field.name]:
                target.type === "checkbox" ? target.checked : target.value,
            }));
        }}
      >
        {row.fields.map((f) => (
          <div key={f.html_name} hidden={!visible(f)}>
            <FieldInput field={{ ...f, required: visible(f) && f.required }} />
          </div>
        ))}
        {row.readonly.map((f) => (
          <div className="field readonly" key={f.name}>
            <label>{f.label}</label>
            <strong>
              <Display value={f.value} />
            </strong>
          </div>
        ))}
      </div>
      {row.errors?.map((e, i) => (
        <p className="field-error" role="alert" key={i}>
          {e}
        </p>
      ))}
    </>
  );
}
export function splitDates(data: FormData, fields: Field[]) {
  for (const f of fields) {
    if (f.split) {
      const date = String(data.get(f.html_name) || "").split("T");
      data.delete(f.html_name);
      data.set(f.html_name + "_0", date[0] || "");
      data.set(f.html_name + "_1", date[1] || "");
    }
  }
}
