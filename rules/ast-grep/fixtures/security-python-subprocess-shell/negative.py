import subprocess


def run_fixed():
    return subprocess.run(["ls", "-l"], capture_output=True)


def run_explicitly_shell_free(cmd):
    return subprocess.run(cmd, shell=False)
