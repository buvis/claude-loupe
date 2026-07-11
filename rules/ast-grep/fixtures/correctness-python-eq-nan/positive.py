import math


def is_missing(value):
    return value == math.nan


def is_sentinel(value):
    return value == float("nan")
