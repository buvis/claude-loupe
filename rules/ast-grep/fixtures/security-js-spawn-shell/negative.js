const { spawn } = require("child_process");

function runFixed() {
  return spawn("ls", ["-l"]);
}

function runShellFree(cmd) {
  return spawn(cmd, [], { shell: false });
}
