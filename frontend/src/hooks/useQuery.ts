import { useEffect, useState } from "react";
export function useQuery<T = any>(
  load: () => Promise<T>,
  keys: unknown[] = [],
) {
  const [data, setData] = useState<T | null>(null),
    [error, setError] = useState<Error | null>(null),
    [loading, setLoading] = useState(true),
    [version, setVersion] = useState(0);
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    load()
      .then((d) => {
        if (active) setData(d);
      })
      .catch((e) => {
        if (active) setError(e);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [...keys, version]);
  return {
    data,
    error,
    loading,
    reload: () => setVersion((n) => n + 1),
    setData,
  };
}
