def run_snippet(snippet):
    return eval(snippet)


def run_code(code):
    exec(code, {"__builtins__": {}})
