from typing import Callable, Dict, Sequence, Tuple, cast

from .promises import promise
from .types import Thenable, ThenableProxy

__all__ = ['barrier']


class barrier(ThenableProxy):
    """Synchronization primitive to call a callback after a list
    of promises have been fulfilled.

    Example:

    .. code-block:: python

        # Request supports the .then() method.
        p1 = http.Request('http://a')
        p2 = http.Request('http://b')
        p3 = http.Request('http://c')
        requests = [p1, p2, p3]

        def all_done():
            ...  # all requests complete

        b = barrier(requests).then(all_done)

        # oops, we forgot we want another request
        b.add(http.Request('http://d'))

    Note that you cannot add new promises to a barrier after
    the barrier is fulfilled.
    """

    def __init__(self, promises: Sequence[Thenable] = None,
                 args: Tuple = None,
                 kwargs: Dict = None,
                 callback: Callable = None,
                 size: int = None) -> None:
        self._set_promise_target(promise())
        self.args = args or ()      # type: Tuple
        self.kwargs = kwargs or {}  # type: Dict
        self._value = 0             # type: int
        self.size = size or 0       # type: int
        self.ready = False          # type: bool
        self.failed = False         # type: bool
        self.cancelled = False      # type: bool
        self.finalized = False      # type: bool
        if not self.size and promises:
            # iter(l) calls len(l) so generator wrappers
            # can only return NotImplemented in the case the
            # generator is not fully consumed yet.
            plen = promises.__len__()
            if plen is not NotImplemented:
                self.size = plen

        if promises:
            self.extend_noincr(promises)
        self.finalized = bool(promises or self.size)
        if callback:
            self.then(callback)

    def __call__(self, *args, **kwargs) -> None:
        if not self.ready and not self.cancelled:
            self._value += 1
            if self.finalized and self._value >= self.size:
                self.ready = True
                self.p(*self.args, **self.kwargs)

    def finalize(self) -> None:
        if not self.finalized and self._value >= self.size:
            self.p(*self.args, **self.kwargs)
        self.finalized = True

    def add(self, p: Thenable) -> None:
        if not self.cancelled:
            self.add_noincr(p)
            self.size += 1

    def add_noincr(self, p: Thenable) -> Thenable:
        if not self.cancelled:
            if self.ready:
                raise ValueError('Cannot add promise to full barrier')
            p.then(cast(Thenable, self))
        return p

    def extend(self, promises: Sequence[Thenable]) -> None:
        if not self.cancelled:
            self.size += len(promises)
            self.extend_noincr(promises)

    def extend_noincr(self, promises: Sequence[Thenable]) -> None:
        if not self.cancelled:
            [self.add_noincr(p) for p in promises]

    @property
    def p(self) -> Thenable:
        return self._p

    @p.setter
    def p(self, p: Thenable) -> None:
        self._p = p
