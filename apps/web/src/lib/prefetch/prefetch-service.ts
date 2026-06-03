/**
 * Background prefetch service.
 *
 * Sections are registered with fetchers and a priority. On app load, the service
 * schedules background fetches one section at a time, storing results in the
 * shared prefetch cache. Components can check the cache to avoid redundant fetches.
 *
 * This ensures each navigation target already has its data loaded and ready.
 */

import { getCachedData, setCachedData, invalidateCache } from "./prefetch-cache";

// ── Types ──────────────────────────────────────────────────────────

export type PrefetchFetcher<T = unknown> = () => Promise<T>;

export type PrefetchSection = {
  /** Stable key used for cache namespacing and deduplication. */
  key: string;
  /** Human-readable label for debugging. */
  label: string;
  /** Higher = loaded sooner. Sections with the same priority run in registration order. */
  priority: number;
  /** Fetchers to call one-by-one for this section. Each stores its result under `key:fetcherName`. */
  fetchers: Array<{ name: string; fn: PrefetchFetcher; ttlMs?: number }>;
  /** Optional delay after this section, to keep background loading polite. */
  cooldownMs?: number;
};

// ── State ───────────────────────────────────────────────────────────

let sections: PrefetchSection[] = [];
let isRunning = false;
let abortController: AbortController | null = null;
let completedSections = new Set<string>();
let queuedSectionKeys: string[] = [];
const DEFAULT_SECTION_COOLDOWN_MS = 250;

// ── Public API ──────────────────────────────────────────────────────

/** Register a section to be prefetched once the service starts. Safe to call at any time. */
export function registerSection(section: PrefetchSection): void {
  // Avoid duplicates
  if (sections.some((s) => s.key === section.key)) return;
  sections.push(section);
}

/** Start background prefetching. Idempotent — subsequent calls are no-ops. */
export function startPrefetching(): void {
  if (isRunning) return;
  isRunning = true;
  abortController = new AbortController();

  // Sort descending by priority so high-priority sections load first.
  const ordered = [...sections].sort((a, b) => b.priority - a.priority);

  // Run sequentially, one fetcher at a time, so we never flood the API.
  runSequentially(ordered, abortController.signal);
}

/** Queue specific sections to warm soon, usually because the user is on or near that route. */
export function warmSections(keys: string[]): void {
  for (const key of keys) {
    if (!sections.some((section) => section.key === key)) continue;
    if (queuedSectionKeys.includes(key)) continue;
    if (isSectionReady(key)) continue;
    queuedSectionKeys.push(key);
  }
  if (!isRunning) startPrefetching();
}

/** Stop any in-progress prefetching. Does not clear the cache. */
export function stopPrefetching(): void {
  abortController?.abort();
  isRunning = false;
  abortController = null;
}

/** Fetch a single section's data now (e.g., on navigation) and cache it. */
export async function prefetchSection(key: string): Promise<void> {
  const section = sections.find((s) => s.key === key);
  if (!section || completedSections.has(key)) return;

  const signal = abortController?.signal;
  for (const fetcher of section.fetchers) {
    if (signal?.aborted) break;
    await waitForIdle(signal);
    await fetchAndCache(section.key, fetcher.name, fetcher.fn, fetcher.ttlMs);
    await sleep(75, signal);
  }
  completedSections.add(key);
}

/** Returns true if all fetchers for the given section have been cached. */
export function isSectionReady(key: string): boolean {
  const section = sections.find((s) => s.key === key);
  if (!section) return false;
  return section.fetchers.every((f) => getCachedData(`${key}:${f.name}`) !== null);
}

/** Invalidate a section's cache and optionally re-prefetch it. */
export function invalidateSection(key: string): void {
  invalidateCache(`${key}:`);
  completedSections.delete(key);
}

/** Reset the service entirely (useful in tests or logout). */
export function resetPrefetchService(): void {
  stopPrefetching();
  sections = [];
  completedSections = new Set();
}

// ── Internal ────────────────────────────────────────────────────────

async function runSequentially(ordered: PrefetchSection[], signal: AbortSignal): Promise<void> {
  while (!signal.aborted) {
    const queuedKey = queuedSectionKeys.shift();
    const section = queuedKey ? sections.find((item) => item.key === queuedKey) : ordered.shift();
    if (!section) break;
    if (signal.aborted) break;

    // Skip sections that are already fully cached.
    if (isSectionReady(section.key)) {
      completedSections.add(section.key);
      continue;
    }

    for (const fetcher of section.fetchers) {
      if (signal.aborted) break;
      await waitForIdle(signal);
      await fetchAndCache(section.key, fetcher.name, fetcher.fn, fetcher.ttlMs);
      await sleep(75, signal);
    }
    completedSections.add(section.key);
    await sleep(section.cooldownMs ?? DEFAULT_SECTION_COOLDOWN_MS, signal);
  }
  isRunning = false;
  abortController = null;
}

async function fetchAndCache<T>(sectionKey: string, fetcherName: string, fn: PrefetchFetcher<T>, ttlMs?: number): Promise<void> {
  const cacheKey = `${sectionKey}:${fetcherName}`;

  // Skip if already cached and valid.
  if (getCachedData(cacheKey) !== null) return;

  try {
    const data = await fn();
    setCachedData(cacheKey, data, ttlMs);
  } catch {
    // Silently fail prefetches — components will fall back to their own fetch logic.
    if (process.env.NODE_ENV !== "production") {
      console.warn(`[prefetch] Failed to prefetch ${cacheKey}`);
    }
  }
}

function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  if (signal?.aborted) return Promise.resolve();
  return new Promise((resolve) => {
    const timer = globalThis.setTimeout(resolve, ms);
    signal?.addEventListener("abort", () => {
      clearTimeout(timer);
      resolve();
    }, { once: true });
  });
}

function waitForIdle(signal?: AbortSignal): Promise<void> {
  if (signal?.aborted || typeof window === "undefined") return Promise.resolve();
  const requestIdle = window.requestIdleCallback;
  if (!requestIdle) return sleep(50, signal);
  return new Promise((resolve) => {
    const id = requestIdle(() => resolve(), { timeout: 600 });
    signal?.addEventListener("abort", () => {
      window.cancelIdleCallback?.(id);
      resolve();
    }, { once: true });
  });
}
