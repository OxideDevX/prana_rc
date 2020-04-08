import asyncio
import bleak

from entity import PranaState, PranaDeviceInfo
from asyncio import AbstractEventLoop
from typing import Dict, NamedTuple, List, Union, Optional


class PranaDeviceManager(object):
    PRANA_DEVICE_NAME_PREFIX = 'PRNAQaq'

    def __init__(self, iface: str = 'hci0', loop: Optional[AbstractEventLoop] = None) -> None:
        self.__ble_interface = iface
        self.__loop = loop
        self.__managed_devices = {}  # type: Dict['str', PranaDevice]

    @classmethod
    def __is_prana_device(cls, dev: "bleak.backends.device.BLEDevice"):
        return dev.name and dev.name.startswith(cls.PRANA_DEVICE_NAME_PREFIX)

    @classmethod
    def __prana_dev_name_2_name(cls, dev_name: str):
        return dev_name.replace(cls.PRANA_DEVICE_NAME_PREFIX, '').strip() if dev_name else dev_name

    @classmethod
    def __addr_for_target(cls, target: Union[str, PranaDeviceInfo]) -> str:
        if isinstance(target, PranaDeviceInfo):
            address = target.address
        elif isinstance(target, str):
            address = target
        else:
            raise ValueError(
                'Device must be specified either by mac address or by PranaDeviceInfo instance')
        return address

    async def discover(self, timeout: int = 5) -> List[PranaDeviceInfo]:
        """
        Listens to devices advertisement for TIMEOUT seconds and returns the list of discovered devices
        :param timeout: time to wait for devices in seconds
        :return: list of discovered devices
        """
        discovered_devs = await bleak.discover(timeout, self.__loop)
        return list(map(lambda dev: PranaDeviceInfo(address=dev.address, bt_device_name=(dev.name or '').strip(),
                                                    name=self.__prana_dev_name_2_name(dev.name), rssi=dev.rssi),
                        filter(PranaDeviceManager.__is_prana_device, discovered_devs)
                        ))

    async def connect(self, target: Union[str, PranaDeviceInfo], timeout: float = 5) -> 'PranaDevice':
        address = self.__addr_for_target(target)
        device = self.__managed_devices.get(address, None)
        if device is None:  # If not found in managed devices list
            device = PranaDevice(address, self.__loop, self.__ble_interface)
            self.__managed_devices[address] = device
        # if not await device.is_connected():
        await device.connect(timeout)
        return device

    async def disconnect_all(self):
        for dev in self.__managed_devices.values():
            await dev.disconnect()


class PranaDevice(object):
    CONTROL_SERVICE_UUID = '0000baba-0000-1000-8000-00805f9b34fb'
    CONTROL_RW_CHARACTERISTIC_UUID = '0000cccc-0000-1000-8000-00805f9b34fb'
    STATE_MSG_PREFIX = b'\xbe\xef'

    class Cmd:
        ENABLE_HIGH_SPEED = bytearray([0xBE, 0xEF, 0x04, 0x07])
        ENABLE_NIGHT_MODE = bytearray([0xBE, 0xEF, 0x04, 0x06])
        TOGGLE_FLOW_LOCK = bytearray([0xBE, 0xEF, 0x04, 0x09])
        TOGGLE_HEATING = bytearray([0xBE, 0xEF, 0x04, 0x05])
        TOGGLE_WINTER_MODE = bytearray([0xBE, 0xEF, 0x04, 0x16])

        SPEED_UP = bytearray([0xBE, 0xEF, 0x04, 0x0C])
        SPEED_DOWN = bytearray([0xBE, 0xEF, 0x04, 0x0B])
        SPEED_IN_UP = bytearray([0xBE, 0xEF, 0x04, 0x0E])
        SPEED_IN_DOWN = bytearray([0xBE, 0xEF, 0x04, 0x0F])
        SPEED_OUT_UP = bytearray([0xBE, 0xEF, 0x04, 0x11])
        SPEED_OUT_DOWN = bytearray([0xBE, 0xEF, 0x04, 0x12])

        FLOW_IN_OFF = bytearray([0xBE, 0xEF, 0x04, 0x0D])
        FLOW_OUT_OFF = bytearray([0xBE, 0xEF, 0x04, 0x10])

        STOP = bytearray([0xBE, 0xEF, 0x04, 0x01])
        READ_STATE = bytearray([0xBE, 0xEF, 0x05, 0x01, 0x00, 0x00, 0x00, 0x00, 0x5A])
        READ_DEVICE_DETAILS = bytearray([0xBE, 0xEF, 0x05, 0x02, 0x00, 0x00, 0x00, 0x00, 0x5A])

    def __init__(self, target: Union[str, PranaDeviceInfo], loop: Optional[AbstractEventLoop] = None,
                 iface: str = 'hci0') -> None:
        self.__address = None
        if isinstance(target, PranaDeviceInfo):
            self.__address = target.address
        elif isinstance(target, str):
            self.__address = target
        else:
            raise ValueError(
                'PranaDevice constructor error: Target must be eithermac address or PranaDeviceInfo instance')
        self.__client = bleak.BleakClient(self.__address, loop, device=iface)
        self.__has_connect_attempts = False

    async def __verify_connected(self):
        if not await self.is_connected():
            raise RuntimeError('Illegal state: device must be connected before running any commands')

    def notification_handler(self, sender, data):
        """Simple notification handler which prints the data received."""
        # print("{0}: {1}".format(sender, data))
        print(self.__parse_state(data))

    async def connect(self, timeout: float = 2):
        # if not await self.is_connected():
        await self.__client.connect(timeout=timeout)
        self.__has_connect_attempts = True
        await self.__client.start_notify(self.CONTROL_RW_CHARACTERISTIC_UUID, self.notification_handler)
        # TODO: Verify prana service exists to ensure it is prana device

    async def disconnect(self):
        await self.__client.disconnect()

    async def is_connected(self):
        if not self.__has_connect_attempts:
            return False
        return await self.__client.is_connected()

    async def _send_command(self, command: bytearray, expect_reply=False) -> bytearray:
        await self.__client.write_gatt_char(self.CONTROL_RW_CHARACTERISTIC_UUID, command, response=True)
        await asyncio.sleep(0.6)
        result = await self.__client.read_gatt_char(self.CONTROL_RW_CHARACTERISTIC_UUID, use_cached=False)
        if expect_reply:
            return result

    async def set_high_speed(self):
        await self.__verify_connected()
        await self._send_command(self.Cmd.ENABLE_HIGH_SPEED)

    async def set_night_mode(self):
        await self.__verify_connected()
        await self._send_command(self.Cmd.ENABLE_NIGHT_MODE)

    async def turn_off(self):
        await self.__verify_connected()
        await self._send_command(self.Cmd.STOP)

    def __parse_state(self, data: bytearray):
        if not data[:2] == self.STATE_MSG_PREFIX:
            return None
        s = PranaState()
        print(data)
        s.speed_locked = int(data[26] / 10)
        s.speed_in = int(data[30] / 10)
        s.speed_out = int(data[34] / 10)
        s.auto_mode = bool(data[20])
        s.night_mode = bool(data[16])
        s.flows_locked = bool(data[22])
        s.is_on = bool(data[10])
        s.mini_heating_enabled = bool(data[14])
        s.winter_mode_enabled = bool(data[42])
        s.is_input_fan_on = bool(data[28])
        s.is_output_fan_on = bool(data[32])
        return s

    async def read_state(self) -> PranaState:
        await self.__verify_connected()
        state_bin = await self._send_command(self.Cmd.READ_STATE, expect_reply=True)
        return self.__parse_state(state_bin)

    async def test_retrieve_state(self):
        async with bleak.BleakClient(self.__address) as client:
            self.__client = client
            return await self.read_state()
