const { exec } = require("child_process");

function gitStatus() {
  exec("git status");
}

function matchInput(pattern, input) {
  return pattern.exec(input);
}
