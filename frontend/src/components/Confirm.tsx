import { useEffect, useId, useRef } from "react";
export function Confirm({
  title,
  details,
  onConfirm,
  onClose,
}: {
  title: string;
  details: any;
  onConfirm: () => void;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  useEffect(() => {
    ref.current?.showModal();
  }, []);
  return (
    <dialog ref={ref} aria-labelledby={titleId} onCancel={onClose}>
      <h2 id={titleId}>{title}</h2>
      <p>Confira os registros afetados antes de continuar.</p>
      <div className="confirmation">
        {Array.isArray(details) ? (
          <ul className="confirmation-list">
            {details.map((detail, index) => (
              <li key={index}>
                {typeof detail === "string" || typeof detail === "number"
                  ? String(detail)
                  : JSON.stringify(detail, null, 2)}
              </li>
            ))}
          </ul>
        ) : typeof details === "string" ? (
          <p>{details}</p>
        ) : (
          <pre>{JSON.stringify(details, null, 2)}</pre>
        )}
      </div>
      <div className="actions">
        <button type="button" autoFocus className="secondary" onClick={onClose}>
          Voltar
        </button>
        <button type="button" className="danger" onClick={onConfirm}>
          Confirmar
        </button>
      </div>
    </dialog>
  );
}
