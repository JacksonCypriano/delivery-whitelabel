import { useEffect, useRef, useState } from "react";
import { request } from "../api/client";
import type { Field } from "../types/forms";
export function RelationshipInput({ field: f }: { field: Field }) {
  const [selected, setSelected] = useState(f.choices),
    [term, setTerm] = useState(""),
    [page, setPage] = useState(1);
  const [options, setOptions] = useState<{ value: string; label: string }[]>(
      [],
    ),
    [more, setMore] = useState(false),
    [error, setError] = useState("");
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => {
    input.current?.setCustomValidity(
      f.required && !selected.length ? "Selecione um registro da lista." : "",
    );
  }, [selected, f.required]);
  useEffect(() => {
    if (f.disabled) return;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      request(`${f.lookup}&q=${encodeURIComponent(term)}&page=${page}`, {
        signal: controller.signal,
      })
        .then((d) => {
          setOptions(d.results);
          setMore(d.more);
          setError("");
        })
        .catch(() => {
          if (!controller.signal.aborted)
            setError("Não foi possível pesquisar os registros.");
        });
    }, 250);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [term, page, f.lookup, f.disabled]);
  return (
    <div>
      {selected.map((c) => (
        <span key={c.value} className="relationship-choice">
          <input
            type="hidden"
            name={f.html_name}
            value={c.value}
            disabled={f.disabled}
          />
          {c.label}{" "}
          <button
            type="button"
            className="text-button"
            disabled={f.disabled}
            aria-label={`Remover ${c.label}`}
            onClick={() =>
              setSelected(selected.filter((s) => s.value !== c.value))
            }
          >
            ×
          </button>
        </span>
      ))}
      <input
        ref={input}
        id={f.html_name}
        aria-label={`Pesquisar ${f.label}`}
        disabled={f.disabled}
        value={term}
        placeholder="Pesquisar e selecionar…"
        onChange={(e) => {
          setTerm(e.target.value);
          setPage(1);
        }}
        autoComplete="off"
      />
      {error && <p role="alert">{error}</p>}
      {!f.disabled && (
        <ul
          aria-label={`Resultados de ${f.label}`}
          className="relationship-results"
        >
          {options.map((c) => (
            <li key={c.value}>
              <button
                type="button"
                className="text-button"
                disabled={selected.some((s) => s.value === c.value)}
                onClick={() => {
                  setSelected(f.multiple ? [...selected, c] : [c]);
                }}
              >
                {c.label}
              </button>
            </li>
          ))}
        </ul>
      )}
      <div className="actions">
        <button
          type="button"
          className="text-button"
          disabled={page <= 1 || f.disabled}
          onClick={() => setPage(page - 1)}
        >
          Anterior
        </button>
        <span>{page}</span>
        <button
          type="button"
          className="text-button"
          disabled={!more || f.disabled}
          onClick={() => setPage(page + 1)}
        >
          Próxima
        </button>
      </div>
    </div>
  );
}
