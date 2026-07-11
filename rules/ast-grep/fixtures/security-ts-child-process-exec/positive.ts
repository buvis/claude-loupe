import { exec } from "child_process";

function removeDir(dir: string): void {
  exec(`rm -rf ${dir}`);
}
