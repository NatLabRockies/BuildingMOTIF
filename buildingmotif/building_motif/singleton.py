from typing import Any


class Singleton(type):
    """Metaclass that makes a class into a singleton."""

    # The single live instance, set on first construction. Declared here so it
    # is statically visible on classes using this metaclass (e.g.
    # ``BuildingMOTIF.instance``) rather than only appearing at runtime.
    instance: Any

    def __call__(cls, *args, **kwargs):
        if not hasattr(cls, "instance"):
            cls.instance = super(Singleton, cls).__call__(*args, **kwargs)
        return cls.instance

    def clean(cls) -> None:
        """Drop the singleton instance so the next construction builds a new one.

        Defined as a metaclass method rather than attached with ``setattr`` in
        ``__new__``: both make ``BuildingMOTIF.clean()`` work at runtime, but
        only this one is visible to a type checker, so callers no longer need
        ``# type: ignore[attr-defined]``.
        """
        if hasattr(cls, "instance"):
            delattr(cls, "instance")


class SingletonNotInstantiatedException(Exception):
    """Raised when a singelton is accessed without being initialized."""
