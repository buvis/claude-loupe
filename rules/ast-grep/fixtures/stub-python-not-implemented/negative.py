import abc


class Transport(abc.ABC):
    @abc.abstractmethod
    def send(self, payload):
        raise NotImplementedError


def guarded(mode):
    if mode == "legacy":
        raise NotImplementedError("legacy mode pending")
    return mode
