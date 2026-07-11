import subprocess


def run_user(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True)


def capture(cmd):
    return subprocess.getoutput(cmd)
