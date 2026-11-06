/** Present backend ISO calendar dates without shifting their day via UTC parsing. */
export function formatDateBR(value: string | null | undefined): string {
  if (!value) return "—";
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  return match ? `${match[3]}/${match[2]}/${match[1]}` : value;
}

export function formatDateTimeBR(value: string | null | undefined): string {
  if (!value) return "—";
  const instant = new Date(value);
  if (Number.isNaN(instant.getTime())) return value;
  return instant.toLocaleString("pt-BR", { timeZone: "America/Sao_Paulo" });
}
