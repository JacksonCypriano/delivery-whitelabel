export function Pagination({ page = 1, pages = 1, size = 10, onPage, onSize }: {
  page?: number;
  pages?: number;
  size?: number;
  onPage: (page: number) => void;
  onSize?: (size: number) => void;
}) {
  return <nav className="pagination" aria-label="Paginação">
    {onSize && <label>Registros por página
      <select value={size} onChange={event => onSize(Number(event.target.value))}>
        {[10, 25, 50, 100].map(value => <option key={value} value={value}>{value}</option>)}
      </select>
    </label>}
    <button type="button" className="secondary" disabled={page <= 1} onClick={() => onPage(page - 1)}>Anterior</button>
    <span aria-live="polite">{page} / {pages}</span>
    <button type="button" className="secondary" disabled={page >= pages} onClick={() => onPage(page + 1)}>Próxima</button>
  </nav>;
}
