import asyncio

from trainer import media


class FakeProc:
    returncode = 0

    async def communicate(self) -> tuple[bytes, bytes]:
        return b"", b""


async def test_commands_run_expected_argv(monkeypatch) -> None:
    calls = []

    async def fake_exec(*argv, **kwargs):
        calls.append(argv)
        return FakeProc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    for action in ("play_pause", "next", "previous", "volume_up", "volume_down"):
        await media.run_media(action)
    assert calls == [
        ("playerctl", "-p", "chrome,chromium", "play-pause"),
        ("playerctl", "-p", "chrome,chromium", "next"),
        ("playerctl", "-p", "chrome,chromium", "previous"),
        ("pactl", "set-sink-volume", "@DEFAULT_SINK@", "+5%"),
        ("pactl", "set-sink-volume", "@DEFAULT_SINK@", "-5%"),
    ]


def test_is_media_action() -> None:
    assert media.is_media_action("next")
    assert not media.is_media_action("ftp_up")
