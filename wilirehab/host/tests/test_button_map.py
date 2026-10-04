from wilirehab import button_map as bm


def test_table_has_no_problems():
    assert bm.problems() == []


def test_every_screen_defines_all_five_buttons():
    for s in bm.SCREENS:
        assert set(s.actions) == set(bm.BUTTONS)


def test_button_order_matches_the_bsp():
    assert bm.BUTTONS == ("gray", "yellow", "green", "blue", "red")


def test_pain_buttons_run_from_minus_two_to_plus_two_with_green_confirming():
    pain = bm.SCREENS_BY_KEY["pain"].actions
    assert [pain[b] for b in bm.BUTTONS] == ["-2", "-1", "OK", "+1", "+2"]


def test_problems_catches_a_long_label(monkeypatch):
    bad = bm._screen("x", "X", "x", None, None, "A label that is far too long", None, "Back")
    monkeypatch.setattr(bm, "SCREENS", bm.SCREENS + (bad,))
    assert any("too long" in p for p in bm.problems())


def test_problems_catches_a_hold(monkeypatch):
    bad = bm._screen("x", "X", "x", None, None, "Hold 3s", None, "Back")
    monkeypatch.setattr(bm, "SCREENS", bm.SCREENS + (bad,))
    assert any("holds" in p for p in bm.problems())
