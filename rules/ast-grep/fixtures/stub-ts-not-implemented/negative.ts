function assertNever(value: never): never {
  throw new Error(`unreachable: ${value}`);
}

function implemented(a: number): number {
  return a * 2;
}
