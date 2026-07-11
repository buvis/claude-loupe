import ast


def constant():
    return eval("2 + 2")


def safe_parse(text):
    return ast.literal_eval(text)


def freeze(model):
    return model.eval()
