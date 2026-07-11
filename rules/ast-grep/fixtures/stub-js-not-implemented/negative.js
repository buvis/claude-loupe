function assertNever(value) {
  throw new Error(`unreachable: ${value}`);
}

function implemented(a) {
  return a * 2;
}
