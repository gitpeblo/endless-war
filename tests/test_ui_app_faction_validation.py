"""`main()`'s `--faction` boundary check.

This does not need a display: validation must reject an unknown faction id
before any Gtk widget is constructed, so importing `endless_war.ui.app` (which
only requires gi/Gtk to be importable, not a live X connection) and calling
`main()` with a bad id is enough. Unlike `test_ui_app.py`, this file is not
gated on `DISPLAY`.
"""

import pytest

from endless_war.ui.app import main


def test_main_rejects_an_unknown_faction_id_before_starting_anything() -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--faction", "999"])
    message = str(exc_info.value)
    assert "999" in message
    assert "0" in message and "4" in message
