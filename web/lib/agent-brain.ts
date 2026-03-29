export function listToLines(items: string[] | undefined | null): string {
  return (items ?? []).join("\n");
}

export function linesToList(value: string): string[] {
  return value
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean);
}
