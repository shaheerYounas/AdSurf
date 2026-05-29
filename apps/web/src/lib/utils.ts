export function cn(...classes: Array<string | false | null | undefined>) {
  return classes.filter(Boolean).join(" ");
}

// Shared classes for native <select> elements: hides the OS chevron and paints
// an inline SVG chevron with 0.75rem right padding so it never touches the edge.
// Apply on every <select> in the app for a consistent look across browsers and themes.
export const selectClasses =
  "appearance-none bg-[length:1rem_1rem] bg-[right_0.75rem_center] bg-no-repeat pr-10 " +
  "bg-[image:url('data:image/svg+xml;charset=UTF-8,%3csvg%20xmlns=%22http://www.w3.org/2000/svg%22%20viewBox=%220%200%2020%2020%22%20fill=%22none%22%20stroke=%22%2364748b%22%20stroke-width=%221.5%22%3e%3cpath%20d=%22M6%208l4%204%204-4%22%20stroke-linecap=%22round%22%20stroke-linejoin=%22round%22/%3e%3c/svg%3e')] " +
  "dark:bg-[image:url('data:image/svg+xml;charset=UTF-8,%3csvg%20xmlns=%22http://www.w3.org/2000/svg%22%20viewBox=%220%200%2020%2020%22%20fill=%22none%22%20stroke=%22%23cbd5e1%22%20stroke-width=%221.5%22%3e%3cpath%20d=%22M6%208l4%204%204-4%22%20stroke-linecap=%22round%22%20stroke-linejoin=%22round%22/%3e%3c/svg%3e')]";

/** Humanizes a snake_case or kebab-case key and fixes known brand names. */
export function humanize(value: string): string {
  const displayNames: Record<string, string> = {
    ai: "AI",
    deepseek: "DeepSeek",
    openai: "OpenAI",
    anthropic: "Anthropic",
    google: "Google",
    roas: "ROAS",
    acos: "ACOS",
    asin: "ASIN",
    sku: "SKU",
    json: "JSON",
    api: "API",
    csv: "CSV",
  };
  const lower = value.toLowerCase();
  if (displayNames[lower]) return displayNames[lower];
  return value
    .replace(/_/g, " ")
    .replace(/-/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}