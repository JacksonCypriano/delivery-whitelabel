import { useEffect, useRef } from "react";
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
  useEffect(() => {
    ref.current?.showModal();
  }, []);
  return (
    <dialog ref={ref} onCancel={onClose}>
      <h2>{title}</h2>
      <p>Confira os registros afetados antes de continuar.</p>
      <div className="confirmation">{JSON.stringify(details, null, 2)}</div>
      <div className="actions">
        <button className="secondary" onClick={onClose}>
          Voltar
        </button>
        <button className="danger" onClick={onConfirm}>
          Confirmar
        </button>
      </div>
    </dialog>
  );
}
