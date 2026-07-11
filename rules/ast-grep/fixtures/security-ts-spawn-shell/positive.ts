import { spawn } from "child_process";

function runUser(cmd: string, args: string[]) {
  return spawn(cmd, args, { shell: true });
}
