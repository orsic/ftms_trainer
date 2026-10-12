"""Control Chrome's media session (MPRIS via playerctl) and system volume (pactl)."""

import asyncio
import logging

log = logging.getLogger(__name__)

PLAYERS = "chrome,chromium"

COMMANDS: dict[str, list[str]] = {
    "play_pause": ["playerctl", "-p", PLAYERS, "play-pause"],
    "next": ["playerctl", "-p", PLAYERS, "next"],
    "previous": ["playerctl", "-p", PLAYERS, "previous"],
    "volume_up": ["pactl", "set-sink-volume", "@DEFAULT_SINK@", "+5%"],
    "volume_down": ["pactl", "set-sink-volume", "@DEFAULT_SINK@", "-5%"],
}


def is_media_action(action: str) -> bool:
    return action in COMMANDS


async def run_media(action: str) -> None:
    proc = await asyncio.create_subprocess_exec(
        *COMMANDS[action], stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE
    )
    _, err = await proc.communicate()
    if proc.returncode:
        log.warning("%s failed: %s", action, err.decode().strip())
