from typing import Any

from vine.promises import promise
from vine.types import Thenable

from .case import Case


class CanThen:

    def then(self, x: Any, y: Any) -> Any:
        ...


class CannotThen:
    ...


class test_Thenable(Case):

    def test_isa(self) -> None:
        self.assertIsInstance(CanThen(), Thenable)
        self.assertNotIsInstance(CannotThen(), Thenable)

    def test_promise(self) -> None:
        self.assertIsInstance(promise(lambda x: x), Thenable)
