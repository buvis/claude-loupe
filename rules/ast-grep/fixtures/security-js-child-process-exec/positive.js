const { exec, execSync } = require("child_process");

function removeDir(dir) {
  exec(`rm -rf ${dir}`);
}

function listDir(dir) {
  return execSync(dir + " --list");
}
