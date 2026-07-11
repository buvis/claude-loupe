const { spawn } = require("child_process");

function runUser(cmd, args) {
  return spawn(cmd, args, { shell: true });
}
