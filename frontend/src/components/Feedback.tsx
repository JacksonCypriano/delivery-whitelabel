import type { ReactNode } from "react";
export function Feedback({
  loading,
  error,
  children,
}: {
  loading?: boolean;
  error?: Error | null;
  children: ReactNode;
}) {
  if (loading)
    return (
      <div className="card" role="status">
        Carregando…
      </div>
    );
  if (error)
    return (
      <div className="alert error" role="alert">
        {error.message}
      </div>
    );
  return <>{children}</>;
}
export function Notice({
  messages,
}: {
  messages?: { level: string; text: string }[];
}) {
  return (
    <>
      {messages?.map((m, i) => (
        <div role="status" className={"alert " + m.level} key={i}>
          {m.text}
        </div>
      ))}
    </>
  );
}
export function Empty() {
  return <div className="empty">Nenhum registro encontrado.</div>;
}
