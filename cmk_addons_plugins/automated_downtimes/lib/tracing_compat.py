#!/usr/bin/env python3

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Callable, Iterator, Protocol, TypeVar, cast

from cmk import trace

FuncT = TypeVar("FuncT", bound=Callable[..., Any])


class _SpanCapableTracer(Protocol):
    def start_as_current_span(self, name: str, *args: Any, **kwargs: Any) -> Any:
        ...


class CompatTracer:
    def __init__(self, tracer: Any) -> None:
        self._tracer = tracer

    def __getattr__(self, name: str) -> Any:
        return getattr(self._tracer, name)

    def instrument(self, _name: str) -> Callable[[FuncT], FuncT]:
        def decorator(func: FuncT) -> FuncT:
            return func

        return decorator

    @contextmanager
    def span(self, name: str, *args: Any, **kwargs: Any) -> Iterator[Any]:
        tracer = cast(_SpanCapableTracer, self._tracer)
        with tracer.start_as_current_span(name, *args, **kwargs) as span:
            yield span


def get_tracer(module_name: str | None = None) -> Any:
    get_tracer_fn = cast(Callable[..., Any], trace.get_tracer)

    try:
        tracer = get_tracer_fn(module_name) if module_name else get_tracer_fn()
    except TypeError:
        tracer = get_tracer_fn()

    if hasattr(tracer, "instrument") and hasattr(tracer, "span"):
        return tracer

    return CompatTracer(tracer)
