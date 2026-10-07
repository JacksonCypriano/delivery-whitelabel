export const actionLabel: Record<string, string> = {
  confirmed: "Confirmar",
  preparing: "Iniciar preparo",
  ready: "Marcar pronto",
  out_for_delivery: "Saiu para entrega",
  delivered: "Marcar entregue",
  cancelled: "Cancelar",
};

export const statusIcon: Record<string, string> = {
  pending: "●",
  confirmed: "✓",
  preparing: "◷",
  ready: "✓",
  out_for_delivery: "→",
  delivered: "✓",
  cancelled: "×",
};

export function money(value: string | number) {
  return Number(value || 0).toLocaleString("pt-BR", {
    style: "currency",
    currency: "BRL",
  });
}

export function localDate(value?: string | null) {
  return value ? new Date(value).toLocaleString("pt-BR") : "—";
}

export function localTime(value?: string | null) {
  return value
    ? new Date(value).toLocaleTimeString("pt-BR", {
        hour: "2-digit",
        minute: "2-digit",
      })
    : "—";
}

export function itemDetails(details: any) {
  if (!details || typeof details !== "object") return [] as string[];
  const lines: string[] = [];
  const add = (rows: any[], prefix = "") => {
    for (const row of rows || []) {
      const group = row.group_name ? `${row.group_name}: ` : "";
      const price = Number(row.price || 0);
      lines.push(
        `${prefix}${group}${row.option_name || "Opção"}${price ? ` (+${money(price)})` : ""}`,
      );
    }
  };
  if (Array.isArray(details.names) && details.names.length) {
    lines.push(`Meio a meio: ${details.names.join(" / ")}`);
  }
  add(details.customizations || []);
  add(details.customizations_whole || [], "Inteira · ");
  add(details.customizations_half1 || [], "1ª metade · ");
  add(details.customizations_half2 || [], "2ª metade · ");
  if (details.notes_half1) lines.push(`1ª metade · ${details.notes_half1}`);
  if (details.notes_half2) lines.push(`2ª metade · ${details.notes_half2}`);
  return lines;
}
