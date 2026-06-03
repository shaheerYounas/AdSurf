/**
 * Lightweight in-memory cache for prefetched API data.
 * Each cache entry stores the data, timestamp, and a TTL.
 * The cache is shared across the app so components can check it before making their own fetch calls.
 */

type CacheEntry<T = unknown> = {
  data: T;
  timestamp: number;
  ttlMs: number;
};

const cache = new Map<string, CacheEntry>();

const DEFAULT_TTL_MS = 5 * 60 * 1000; // 5 minutes

export function getCachedData<T>(key: string): T | null {
  const entry = cache.get(key);
  if (!entry) return null;
  if (Date.now() - entry.timestamp > entry.ttlMs) {
    cache.delete(key);
    return null;
  }
  return entry.data as T;
}

export function setCachedData<T>(key: string, data: T, ttlMs = DEFAULT_TTL_MS): void {
  cache.set(key, { data, timestamp: Date.now(), ttlMs });
}

export function clearCache(): void {
  cache.clear();
}

export function invalidateCache(prefix: string): void {
  for (const key of cache.keys()) {
    if (key.startsWith(prefix)) cache.delete(key);
  }
}