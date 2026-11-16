import { useEffect, useId, useRef } from "react";
export function Confirm({
  title,
  details,
  onConfirm,
  onClose,
  confirmLabel = "Confirmar",
  cancelLabel = "Voltar",
  description = "Confira os registros afetados antes de continuar.",
  hideConfirm = false,
}: {
  title: string;
  details: any;
  onConfirm: () => void;
  onClose: () => void;
  confirmLabel?: string;
  cancelLabel?: string;
  description?: string;
  hideConfirm?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  useEffect(() => {
    const dialog = ref.current;
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    if (dialog && !dialog.open) dialog.showModal();
    return () => {
      if (dialog?.open) dialog.close();
      if (previous?.isConnected) previous.focus();
    };
  }, []);
  return (
    <dialog ref={ref} aria-labelledby={titleId} onCancel={onClose}>
      <h2 id={titleId}>{title}</h2>
      {description && <p>{description}</p>}
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
          {cancelLabel}
        </button>
        {!hideConfirm && <button type="button" className="danger" onClick={onConfirm}>
          {confirmLabel}
        </button>}
      </div>
    </dialog>
  );
}
