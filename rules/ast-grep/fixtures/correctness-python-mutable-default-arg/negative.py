def gather(item, bucket=None):
    if bucket is None:
        bucket = []
    bucket.append(item)
    return bucket


def window(size=10, anchor=()):
    return (size, anchor)
