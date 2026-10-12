import pytest

from trainer.click import Click
from trainer.devices import BleDevices
from trainer.ftms import Trainer
from trainer.sensors import Sensor

ENV = {
    "TRAINER_ADDR": "AA:01",
    "POWER_METER_ADDR": "AA:02",
    "HEART_RATE_ADDR": "",
    "CLICK_ADDR": "AA:04",
}


def test_from_env_requires_trainer() -> None:
    with pytest.raises(ValueError, match="TRAINER_ADDR"):
        BleDevices.from_env({**ENV, "TRAINER_ADDR": ""})


def test_build_real_devices() -> None:
    actions = []
    d = BleDevices.from_env(ENV).build(actions.append)
    assert isinstance(d.trainer, Trainer) and d.trainer.address == "AA:01"
    assert isinstance(d.power_meter, Sensor) and d.power_meter.address == "AA:02"
    assert d.heart_rate.status == "off"  # no address configured
    assert isinstance(d.click, Click) and d.click.address == "AA:04"
    d.click._on_action("next")
    assert actions == ["next"]
    assert d.tick_interval == 1.0
