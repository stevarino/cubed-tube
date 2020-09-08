
from models import Series, Channel

from copy import copy
from dataclasses import dataclass, field
from typing import List

@dataclass
class Cost():
    value: int = 0

    def add(self,  other: int):
        self.value += other
        return self.value

@dataclass
class Context:
    api_key: str = ''
    cost: Cost  = field(default_factory=Cost)
    series: Series = None
    channel: Channel = None
    channels: List[str] = field(default_factory=list)

    def copy(self, **kwargs):
        other = copy(self)
        for key, val in kwargs.items():
            setattr(other, key, val)
        return other
