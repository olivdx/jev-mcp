from enum import Enum


class Transport(str, Enum):
    STDIO = "stdio"
    HTTP = "http"
