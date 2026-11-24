// Another runtime's exec(program, args): it starts no shell, and this file never
// names child_process. A bare `exec` here is not Node's.
import { exec } from "herdr";

export async function currentBranch(program, cwd) {
  return exec(program, ["branch", "--show-current"], { cwd });
}

export function run(cmd, args, options) {
  return exec(cmd, args, options);
}
