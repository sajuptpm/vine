import sys

from collections import deque
from types import TracebackType
from typing import (
    Any, Callable, Dict, MutableSequence, Sequence, Tuple, cast,
)

from .types import PromiseT, ImmutablePromise

__all__ = ['promise']


class promise(ImmutablePromise):
    """Future evaluation.

    This is a special implementation of promises in that it can
    be used both for "promise of a value" and lazy evaluation.
    The biggest upside for this is that everything in a promise can also be
    a promise, e.g. filters, callbacks and errbacks can all be promises.

    Usage examples:

    .. code-block:: python

        >>> from __future__ import print_statement  # noqa
        >>> p = promise()
        >>> p.then(promise(print, ('OK',)))  # noqa
        >>> p.on_error = promise(print, ('ERROR',))  # noqa
        >>> p(20)
        OK, 20
        >>> p.then(promise(print, ('hello',)))  # noqa
        hello, 20


        >>> p.throw(KeyError('foo'))
        ERROR, KeyError('foo')


        >>> p2 = promise()
        >>> p2.then(print)  # noqa
        >>> p2.cancel()
        >>> p(30)

    Example:

    .. code-block:: python

        from vine import promise, wrap

        class Protocol:

            def __init__(self):
                self.buffer = []

            def receive_message(self):
                return self.read_header().then(
                    self.read_body).then(
                        wrap(self.prepare_body))

            def read(self, size, callback=None):
                callback = callback or promise()
                tell_eventloop_to_read(size, callback)
                return callback

            def read_header(self, callback=None):
                return self.read(4, callback)

            def read_body(self, header, callback=None):
                body_size, = unpack('>L', header)
                return self.read(body_size, callback)

            def prepare_body(self, value):
                self.buffer.append(value)

    """
    cancelled = False
    ready = False
    failed = False
    fun = None        # type: PromiseT
    value = None      # type: Any
    reason = None     # type: BaseException

    def __init__(self, fun: PromiseT = None,
                 args: Sequence = None,
                 kwargs: Dict = None,
                 callback: PromiseT = None,
                 on_error: PromiseT = None,
                 cancelled: bool = False,
                 ready: bool = False,
                 failed: bool = False,
                 value: Any = None,
                 reason: BaseException = None,
                 _svpending: ImmutablePromise = None,
                 _lvpending: Sequence[ImmutablePromise] = None) -> None:
        self.fun = fun                          # type: PromiseT
        self.args = cast(Sequence, args or ())  # type: Sequence
        self.kwargs = kwargs or {}              # type: Dict
        self.cancelled = cancelled              # type: bool
        self.ready = ready                      # type: bool
        self.failed = failed                    # type: bool
        self.value = value                      # type: bool
        self.reason = reason                # type: BaseException
        self._svpending = _svpending        # type: ImmutablePromise
        self._lvpending = None              # type: deque[ImmutablePromise]
        self.on_error = on_error            # type: PromiseT

        if callback is not None:
            self.then(callback)

        if self.fun:
            assert callable(fun)

    def partial(self, *args, **kwargs) -> ImmutablePromise:
        return self.clone(args=args, kwargs=kwargs)

    def partial_inplace(self, *args, **kwargs) -> None:
        if args:
            self.args = args + cast(Tuple, self.args)
        if kwargs:
            self.kwargs.update(kwargs)

    def clone(self, args: Tuple[Any, ...]=(),
              kwargs: Dict={}) -> ImmutablePromise:
        return type(self)(
            self.fun,
            args + cast(Tuple, self.args) if args else self.args,
            dict(self.kwargs, **kwargs) if kwargs else self.kwargs,
            cancelled=self.cancelled,
            ready=self.ready,
            failed=self.failed,
            value=self.value,
            reason=self.reason,
            _svpending=self._svpending,
            _lvpending=self._lvpending,
        )

    def __copy__(self):
        return self.clone()

    def cancel(self) -> None:
        self.cancelled = True
        try:
            if self._svpending is not None:
                self._svpending.cancel()
            if self._lvpending is not None:
                for pending in self._lvpending:
                    pending.cancel()
            if isinstance(self.on_error, ImmutablePromise):
                self.on_error.cancel()
        finally:
            self._svpending = self._lvpending = self.on_error = None

    def __call__(self, *args, **kwargs) -> Any:
        if self.cancelled:
            return
        ca = ()  # type: Sequence
        ck = {}  # type: Dict
        retval = None  # type: Any
        final_args = (cast(Tuple, self.args) + cast(Tuple, args) if args
                      else self.args)  # type: Sequence
        final_kwargs = (dict(self.kwargs, **kwargs) if kwargs
                        else self.kwargs)  # type: Dict
        if self.fun:
            try:
                retval = cast(Callable, self.fun)(*final_args, **final_kwargs)
                ca = (retval,)
                ck = {}
                self.value = (ca, ck)
            except Exception:
                return self.throw()
            except BaseException:
                # reraise SystemExit and friends in context of promise.
                if self.cancelled:
                    raise
                return self.throw()
        else:
            ca = final_args
            ck = final_kwargs
            self.value = (ca, ck)
        self.ready = True
        svpending = self._svpending
        if svpending is not None:
            try:
                svpending(*ca, **ck)
            finally:
                self._svpending = None
        else:
            lvpending = self._lvpending
            try:
                while lvpending:
                    p = lvpending.popleft()
                    p(*ca, **ck)
            finally:
                self._lvpending = None
        return retval

    def then(self, callback: PromiseT,
             on_error: PromiseT = None) -> ImmutablePromise:
        p = cast(ImmutablePromise, callback)
        if not isinstance(p, ImmutablePromise):
            p = type(self)(callback, on_error=on_error)
        if self.cancelled:
            p.cancel()
            return p
        if self.failed:
            p.throw(self.reason)
        elif self.ready:
            args, kwargs = self.value
            p(*args, **kwargs)
        if self._lvpending is None:
            svpending = self._svpending
            if svpending is not None:
                self._svpending, self._lvpending = None, deque([svpending])
            else:
                self._svpending = p
                return p
        self._lvpending.append(p)
        return p

    def throw1(self, exc: BaseException = None) -> None:
        if not self.cancelled:
            exc = exc if exc is not None else sys.exc_info()[1]
            self.failed, self.reason = True, exc
            if self.on_error:
                self.on_error(*cast(Tuple, self.args) + (exc,), **self.kwargs)

    def throw(self, exc: BaseException = None,
              tb: TracebackType = None,
              propagate: int = True) -> None:
        if not self.cancelled:
            current_exc = sys.exc_info()[1]
            exc = exc if exc is not None else current_exc
            try:
                self.throw1(exc)
                svpending = self._svpending
                if svpending is not None:
                    try:
                        svpending.throw1(exc)
                    finally:
                        self._svpending = None
                else:
                    lvpending = self._lvpending
                    try:
                        while lvpending:
                            lvpending.popleft().throw1(exc)
                    finally:
                        self._lvpending = None
            finally:
                if self.on_error is None and propagate:
                    if tb is None and (exc is None or exc is current_exc):
                        raise
                    raise exc.with_traceback(tb)

    def __repr__(self) -> str:
        return ('<{0} --> {1!r}>' if self.fun else '<{0}>').format(
            '{0}@0x{1:x}'.format(
                type(self).__qualname__, id(self)), self.fun,
        )

    @property
    def listeners(self) -> MutableSequence:
        if self._lvpending:
            return self._lvpending
        return [self._svpending]
