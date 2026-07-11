import { exec } from "child_process";

function gitStatus(): void {
  exec("git status");
}

function matchInput(pattern: RegExp, input: string): RegExpExecArray | null {
  return pattern.exec(input);
}
