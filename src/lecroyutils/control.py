import re
from enum import Enum
from typing import AnyStr, Dict, Union

import vxi11

from .data import LecroyScopeData


VBSValue = Union[str, int, float]


def _escape(value: VBSValue) -> str:
    if isinstance(value, str):
        return f'"{value}"'
    return repr(value)


def _unpack_response(res: str) -> str:
    if res[:4].upper() == 'VBS ':
        return res[4:]
    return res


class TriggerMode(Enum):
    stopped = 'Stopped'
    single = 'Single'
    normal = 'Normal'
    auto = 'Auto'


class TriggerType(Enum):
    edge = 'EDGE'
    width = 'WIDTH'
    qualified = 'QUALIFIED'
    window = 'WINDOW'
    internal = 'INTERNAL'
    tv = 'TV'
    pattern = 'PATTERN'


class LecroyScope:
    """
    Allows to control a lecroy oscilloscopes per vxi11.

    The remote connection settings in the oscilloscope must be set to vxi11.
    """

    def __init__(self, ip: str) -> None:
        """
        Connects to an oscilloscope defined by the given ip.

        :param ip: the ip address of the oscilloscope to connect to
        """
        self.available_channels = []
        self.available_parameters = []

        self.scope = vxi11.Instrument(ip)
        self._parse_available_resources()

    def _action(self, action: str):
        self.scope.write(f'VBS \'{action}\'')

    def _method(self, method: str, *args: VBSValue, timeout: float = None) -> str:
        old_timeout = self.scope.timeout
        if timeout is not None:
            self.scope.timeout = timeout + old_timeout

        arg_string = ', '.join(map(_escape, args))
        self.scope.write(f'VBS? \'return = {method}({arg_string})\'')
        response = _unpack_response(self.scope.read())

        self.scope.timeout = old_timeout
        return response

    def _set(self, var: str, value: VBSValue):
        self.scope.write(f'VBS \'{var} = {_escape(value)}\'')

    def _read(self, var: str) -> str:
        self.scope.write(f'VBS? \'return = {var}\'')
        return _unpack_response(self.scope.read())

    def is_idle(self) -> str:
        return self._method('app.WaitUntilIdle', 5)

    def _parse_available_resources(self):
        for resource in self._read('app.ExecsNameAll').split(','):
            if re.match(r"C\d.*", resource):
                self.available_channels.append(resource)
            elif re.match(r"P\d.*", resource):
                self.available_parameters.append(resource)

    def check_source(self, source: str):
        # currently no digital channels supported
        self.check_channel(source)

    def check_channel(self, channel: str):
        if channel.upper() not in self.available_channels:
            raise Exception(f'Channel {channel} not available.')

    def check_parameter(self, parameter: str):
        if parameter.upper() not in self.available_parameters:
            raise Exception(f'Parameter {parameter} not available.')

    def acquire(self, timeout: float = 0.1, force=False) -> bool:
        return self._method('app.Acquisition.acquire', timeout, force, timeout=timeout) == '1'

    @property
    def trigger_mode(self) -> TriggerMode:
        return TriggerMode(self._read('app.Acquisition.TriggerMode'))

    @trigger_mode.setter
    def trigger_mode(self, mode: TriggerMode):
        self._set('app.Acquisition.TriggerMode', mode.value)

    @property
    def trigger_source(self) -> str:
        return self._read('app.Acquisition.Trigger.Source')

    @trigger_source.setter
    def trigger_source(self, source: str):
        if source.upper() not in ['EXT', 'LINE']:
            self.check_source(source)
        self._set('app.Acquisition.Trigger.Source', source.upper())

    @property
    def trigger_type(self) -> TriggerType:
        return TriggerType(self._read('app.Acquisition.Trigger.Type'))

    @trigger_type.setter
    def trigger_type(self, new_type: TriggerType):
        self._set('app.Acquisition.Trigger.Type', new_type.value)

    @property
    def trigger_level(self) -> str:
        return self._read(f'app.Acquisition.Trigger.{self.trigger_source}.Level')

    @trigger_level.setter
    def trigger_level(self, level: VBSValue):
        source = self.trigger_source
        if source.upper() not in ['EXT', *self.available_channels]:
            raise NotImplementedError(f'Setting of trigger_level not supported for current trigger_source ({source}).')

        self._set(f'app.Acquisition.Trigger.{source}.Level', level)

    def clear_statistics(self):
        self._action('app.Measure.ClearSweeps')

    def statistics(self, parameter: str) -> Dict[str, str]:
        self.check_parameter(parameter)
        return {
            'last': self._read(f'app.Measure.{parameter}.last.Result.Value'),
            'max': self._read(f'app.Measure.{parameter}.max.Result.Value'),
            'mean': self._read(f'app.Measure.{parameter}.mean.Result.Value'),
            'min': self._read(f'app.Measure.{parameter}.min.Result.Value'),
            'num': self._read(f'app.Measure.{parameter}.num.Result.Value'),
            'sdev': self._read(f'app.Measure.{parameter}.sdev.Result.Value'),
            'status': self._read(f'app.Measure.{parameter}.Out.Result.Status')
        }

    def _screenshot_raw(self) -> bytes:
        self.scope.write("HCSU DEV, PNG, FORMAT, PORTRAIT, BCKG, WHITE, DEST, REMOTE, PORT, NET, AREA, GRIDAREAONLY")
        self.scope.write("SCDP")
        return self.scope.read_raw()

    def save_screenshot(self, file_path: AnyStr):
        with open(file_path, 'wb') as f:
            f.write(self._screenshot_raw())

    def _waveform_raw(self, source: str) -> bytes:
        self.check_source(source)
        self.scope.write(f'{source}:WF?')
        return self.scope.read_raw()

    def waveform(self, source: str) -> LecroyScopeData:
        return LecroyScopeData(self._waveform_raw(source), source_desc=f'{source}-live')

    def save_waveform(self, source: str, file_path: AnyStr):
        with open(file_path, 'wb') as f:
            f.write(self._waveform_raw(source))

    def save_waveform_on_lecroy(self):
        self._action('app.SaveRecall.Waveform.SaveFile')
