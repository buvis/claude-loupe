import { spawn } from "child_process";

function runFixed() {
  return spawn("ls", ["-l"]);
}

function runShellFree(cmd: string) {
  return spawn(cmd, [], { shell: false });
}
