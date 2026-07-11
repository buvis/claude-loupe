import json
import pickle


def roundtrip():
    return pickle.loads(b"\x80\x04N.")


def parse(text):
    return json.loads(text)
