function readSettings(path: string): string | undefined {
  try {
    return load(path);
  } catch {}
}
