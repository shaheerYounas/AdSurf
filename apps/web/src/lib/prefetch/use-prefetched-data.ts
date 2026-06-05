/**
 * React hook that consumes prefetched data from the cache.
 *
 * On first render, it checks the in-memory cache. If the data is already
 * there (prefetched in the background), it returns immediately with no
 * loading state. Otherwise, it falls back to the provided fetcher function
 * and populates the cache for future use.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { formatApiError } from "@/lib/api/client";
import { getCachedData, setCachedData } from "./prefetch-cache";

export type UsePrefetchedDataResult<T> = {
  data: T | null;
  isLoading: boolean;
  error: string | null;
  /** Manually refetch and update the cache. */
  refetch: () => Promise<void>;
};

/**
 * Hook to consume data that may already have been prefetched.
 *
 * @param cacheKey  - The full cache key (e.g., "dashboard:summary").
 * @param fetcher   - Fallback fetcher used if data is not cached.
 * @param ttlMs     - Cache TTL in ms (default 5 min).
 */
export function usePrefetchedData<T>(
  cacheKey: string,
  fetcher: () => Promise<T>,
  ttlMs?: number,
): UsePrefetchedDataResult<T> {
  const [data, setData] = useState<T | null>(() => getCachedData<T>(cacheKey));
  const [isLoading, setIsLoading] = useState<boolean>(!data);
  const [error, setError] = useState<string | null>(null);
  const fetcherRef = useRef(fetcher);
  const cacheKeyRef = useRef(cacheKey);

  useEffect(() => {
    fetcherRef.current = fetcher;
    cacheKeyRef.current = cacheKey;
  }, [cacheKey, fetcher]);

  const load = useCallback(async () => {
    // Re-check cache (may have been populated by prefetch since mount)
    const cached = getCachedData<T>(cacheKeyRef.current);
    if (cached) {
      setData(cached);
      setIsLoading(false);
      return;
    }

    setIsLoading(true);
    setError(null);
    try {
      const result = await fetcherRef.current();
      setCachedData(cacheKeyRef.current, result, ttlMs);
      setData(result);
    } catch (caught) {
      setError(formatApiError(caught, "Data could not be loaded."));
    } finally {
      setIsLoading(false);
    }
  }, [ttlMs]);

  useEffect(() => {
    // Only fetch if we don't already have cached data.
    if (data !== null) return;
    void load();
  }, [data, load]);

  return { data, isLoading, error, refetch: load };
}
