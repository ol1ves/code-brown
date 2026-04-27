"""Exception hierarchy unit tests."""

from __future__ import annotations

import pytest

from xscraper.exceptions import (
    XAuthError,
    XConfigError,
    XError,
    XRateLimit,
    XSchemaError,
)


@pytest.mark.parametrize(
    "cls",
    [XConfigError, XAuthError, XRateLimit, XSchemaError],
)
def test_subclass_of_xerror(cls):
    assert issubclass(cls, XError)
    assert issubclass(XError, Exception)


def test_messages_propagate():
    with pytest.raises(XAuthError, match="bad cookies"):
        raise XAuthError("bad cookies")
