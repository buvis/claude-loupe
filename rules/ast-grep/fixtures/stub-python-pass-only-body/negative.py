import abc


class Port(abc.ABC):
    @abc.abstractmethod
    def send(self, payload):
        pass


def implemented(value):
    return value * 2
