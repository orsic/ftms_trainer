from trainer.click import (
    ACTIONS,
    BUTTON_BITS,
    ButtonDecoder,
    action_for,
    encode_varint,
    parse_pressed_mask,
)


def keypad_frame(pressed_bits: list[int]) -> bytes:
    mask = 0xFFFFFFFF
    for b in pressed_bits:
        mask &= ~(1 << b)
    # 0x23 message id, field 1 (varint) = active-low mask, then an analog sub-message (field 2) to skip
    return bytes([0x23, 0x08]) + encode_varint(mask) + bytes([0x12, 0x02, 0x08, 0x00])


def test_varint_roundtrip_via_frame() -> None:
    assert parse_pressed_mask(keypad_frame([])) == 0
    assert parse_pressed_mask(keypad_frame([4, 12])) == (1 << 4) | (1 << 12)


def test_non_keypad_messages_ignored() -> None:
    assert parse_pressed_mask(bytes([0x19, 0x08, 0x01])) is None
    assert parse_pressed_mask(b"RideOn") is None
    assert parse_pressed_mask(b"") is None


def test_short_and_long_press_emitted_on_release() -> None:
    d = ButtonDecoder({"A": 4, "PLUS": 12}, long_press=0.6)
    assert d.feed(1 << 4, 0.0) == []
    assert d.feed(0, 0.2) == [("A", False)]
    assert d.feed(1 << 12, 1.0) == []
    assert d.feed(1 << 12, 1.5) == []  # still held, repeated frame
    assert d.feed(0, 1.7) == [("PLUS", True)]


def test_two_buttons_released_together() -> None:
    d = ButtonDecoder({"A": 4, "B": 5})
    d.feed((1 << 4) | (1 << 5), 0.0)
    assert sorted(d.feed(0, 0.1)) == [("A", False), ("B", False)]


def test_action_mapping() -> None:
    assert action_for("PLUS", False) == "ftp_up"
    assert action_for("PLUS", True) == "ftp_down"
    assert action_for("Z", True) == "previous"
    assert action_for("A", True) == "play_pause"  # no long action -> falls back to short
    assert set(BUTTON_BITS) == {b for b, _ in ACTIONS}
