from typing import Any, Callable, Dict, Optional, Tuple, cast

from .promises import promise
from .types import Thenable, PromiseT, ImmutablePromise, Throwable

__all__ = [
    'maybe_promise', 'ensure_promise',
    'ppartial', 'preplace', 'ready_promise',
    'starpromise', 'transform', 'wrap',
]


def maybe_promise(p: Optional[PromiseT]) -> ImmutablePromise:
    if p and not isinstance(p, ImmutablePromise):
        return promise(p)
    return cast(ImmutablePromise, p)


def ensure_promise(p: Optional[PromiseT]) -> ImmutablePromise:
    if p is None:
        return promise()
    return cast(ImmutablePromise, maybe_promise(p))


def ppartial(p: Optional[PromiseT], *args, **kwargs) -> ImmutablePromise:
    _p = ensure_promise(p)
    _p.partial_inplace(*args, **kwargs)
    return _p


def preplace(p: PromiseT, *args, **kwargs) -> ImmutablePromise:

    def _replacer(*_, **__) -> Any:
        return p(*args, **kwargs)
    return promise(_replacer)


def ready_promise(callback: PromiseT = None, *args) -> Any:
    p = ensure_promise(callback)
    p(*args)
    return p


def starpromise(fun: PromiseT, *args, **kwargs) -> ImmutablePromise:
    return promise(fun, args, kwargs)


def transform(filter_: PromiseT, callback: PromiseT,
              *filter_args, **filter_kwargs) -> ImmutablePromise:
    """Filter final argument to a promise.

    E.g. to coerce callback argument to :class:`int`::

        transform(int, callback)

    or a more complex example extracting something from a dict
    and coercing the value to :class:`float`:

    .. code-block:: python

        def filter_key_value(key, filter_, mapping):
            return filter_(mapping[key])

        def get_page_expires(self, url, callback=None):
            return self.request(
                'GET', url,
                callback=transform(get_key, callback, 'PageExpireValue', int),
            )

    """
    pcallback = ensure_promise(callback)
    P = promise(_transback, (   # type: ImmutablePromise
        filter_, pcallback, filter_args, filter_kwargs,
    ))
    P.then(promise(), cast(ImmutablePromise, pcallback.throw))
    return P


def _transback(filter_: PromiseT, callback: Throwable,
               args: Tuple[Any, ...], kwargs: Dict, ret: Any) -> Any:
    try:
        ret = filter_(*args + (ret,), **kwargs)
    except Exception:
        callback.throw()
    else:
        return cast(Callable, callback)(ret)


def wrap(p: PromiseT):
    """Wrap promise so that if the promise is called with a promise as
    argument, we attach ourselves to that promise instead."""

    def on_call(*args, **kwargs) -> Any:
        if len(args) == 1 and isinstance(args[0], Thenable):
            return args[0].then(p)
        else:
            return p(*args, **kwargs)

    return on_call
