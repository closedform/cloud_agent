"""Handler protocol and registry."""

from typing import Callable, Protocol

from src.config import Config
from src.models import Task
from src.services import Services


class HandlerFunc(Protocol):
    """Protocol defining handler function signature."""

    def __call__(self, task: Task, config: Config, services: Services) -> None:
        """Handle a task.

        Args:
            task: The task to handle.
            config: Application configuration.
            services: Initialized external services.
        """
        ...


# Global handler registry
HANDLERS: dict[str, HandlerFunc] = {}


def register_handler(intent: str) -> Callable[[HandlerFunc], HandlerFunc]:
    """Decorator to register a handler for an intent.

    Example:
        @register_handler("schedule")
        def handle_schedule(task: Task, config: Config, services: Services) -> None:
            ...
    """

    def decorator(func: HandlerFunc) -> HandlerFunc:
        HANDLERS[intent] = func
        return func

    return decorator


def get_handler(intent: str) -> HandlerFunc | None:
    """Get the handler for an intent, or None if not found."""
    return HANDLERS.get(intent)
