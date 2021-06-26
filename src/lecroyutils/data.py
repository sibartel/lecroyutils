import sys
from datetime import datetime
from typing import AnyStr
from warnings import warn

import numpy as np


class DataCorruptException(Exception):
    """
    The provided data is corrupt and therefore not parsable.
    """
    pass


class LecroyScopeData(object):
    """
    Represents parsed waveform data from lecroy oscilloscopes.

    The data can be either directly passed to the constructor or the static method
    `LecroyScopeData.parse_file` can be used to parse a .trc file.
    """

    @staticmethod
    def parse_file(filepath: str, *kargs, **kwargs) -> 'LecroyScopeData':
        """
        Reads the provided file and parses the data as `LecroyScopeData`.

        The `LecroyScopeData.source_desc` is set to the provided filepath in the
        returned `LecroyScopeData` instance.

        :param filepath: file to read
        :param kargs: arguments are directly passed to `LecroyScopeData.__init__`
        :param kwargs: arguments are directly passed to `LecroyScopeData.__init__`
        :return: `LecroyScopeData` instance
        """
        with open(filepath, 'rb') as file:
            return LecroyScopeData(file.read(), *kargs, source_desc=filepath, **kwargs)

    def __init__(self, data: AnyStr, sparse: int = None, source_desc: str = '') -> None:
        """
        Parse the provided `data` as waveform data from a lecroy oscilloscope.

        :param data: the data to be parsed
        :param sparse: if set the waveform data is sparse decoded
        :param source_desc: can be used to track the origin of the provided data
        """
        self.data = data
        self.source_desc = source_desc

        self.endianness = "<"

        try:
            # convert the first 50 bytes to a string to find position of substring WAVEDESC
            self._pos_wavedesc = self.data[:50].decode("ascii", "replace").index("WAVEDESC")

            self._comm_order = self._parse_int16(34)  # big endian (>) if 0, else little
            self.endianness = [">", "<"][self._comm_order]

            self.template_name = self._parse_string(16)
            self._comm_type = self._parse_int16(32)  # encodes whether data is stored as 8 or 16bit

            self.len_wavedesc = self._parse_int32(36)
            self.len_usertext = self._parse_int32(40)
            self.len_triggertime_array = self._parse_int32(48)
            self.len_wave_array_1 = self._parse_int32(60)

            self.instrument_name = self._parse_string(76)
            self.instrument_number = self._parse_int32(92)

            # self.traceLabel = "NOT PARSED"  # 96
            self.count_wave_array = self._parse_int32(116)
            self.subarray_count = self._parse_int32(144)

            self.vertical_gain = self._parse_float(156)
            self.vertical_offset = self._parse_float(160)
            self.y_max = self.vertical_gain * self._parse_float(164) - self.vertical_offset
            self.y_min = self.vertical_gain * self._parse_float(168) - self.vertical_offset

            self.nominal_bits = self._parse_int16(172)

            self.horizontal_interval = self._parse_float(176)
            self.horizontal_offset = self._parse_double(180)

            self.y_unit = self._parse_string(196, 48)
            self.x_unit = self._parse_string(244, 48)

            self.trigger_time = self._parse_timestamp(296)
            self.record_type = ["single_sweep", "interleaved", "histogram", "graph",
                                "filter_coefficient", "complex", "extrema", "sequence_obsolete",
                                "centered_RIS", "peak_detect"][self._parse_int16(316)]
            self.processing_done = ["No Processing", "FIR Filter", "interpolated", "sparsed",
                                    "autoscaled", "no_results", "rolling", "cumulative"][self._parse_int16(318)]
            self.timebase = self._parse_timebase(324)

            self.Ts = self.horizontal_interval
            self.fs = 1 / self.horizontal_interval

            self.vertical_coupling = ["DC50", "GND", "DC1M", "GND", "AC1M"][self._parse_int16(326)]
            self.bandwidth_limit = ["off", "on"][self._parse_int16(334)]
            self.wave_source = ["C1", "C2", "C3", "C4", "ND"][self._parse_int16(344)]

            start = self._pos_wavedesc + self.len_wavedesc + self.len_usertext + self.len_triggertime_array
            type_identifier = self.endianness + ("i1" if self._comm_type == 0 else "i2")
            self.y = np.frombuffer(self.data[start:start + self.len_wave_array_1],
                                   dtype=np.dtype((type_identifier, self.count_wave_array)), count=1)[0]
            self.x = np.linspace(
                0, self.count_wave_array * self.horizontal_interval, num=self.count_wave_array
            ) + self.horizontal_offset

            self.is_sequence = self.subarray_count > 1
            if self.is_sequence:
                # Sequence Mode
                start = self._pos_wavedesc + self.len_wavedesc + self.len_usertext
                interleaved_data = np.frombuffer(
                    self.data[start:start + self.len_triggertime_array],
                    dtype=np.dtype((self.endianness + "f8", 2 * self.subarray_count)),
                    count=1
                )[0]
                self.trigger_times = interleaved_data[::2]
                self.trigger_offsets = interleaved_data[1::2]

                points_per_subarray = int(self.count_wave_array / self.subarray_count)

                self.y = self.y.reshape(self.subarray_count, points_per_subarray).T

                self.x = np.tile(np.linspace(
                    0, points_per_subarray * self.horizontal_interval, num=points_per_subarray
                ) + self.horizontal_offset, (self.subarray_count, 1)) + self.trigger_times.reshape((-1, 1))
                self.x = self.x.T

            # now scale the ADC values
            self.y = self.vertical_gain * np.array(self.y) - self.vertical_offset

            self.clipped = np.amax(self.y) > self.y_max or np.amin(self.y) < self.y_min
            if self.clipped:
                warn(f'Signal was clipped: {self.source_desc}')

            if sparse is not None:
                indices = int(len(self.x) / sparse) * np.arange(sparse)

                self.x = self.x[indices]
                self.y = self.y[indices]

        except (ValueError, IndexError):
            raise DataCorruptException(f'Data corrupt: {self.source_desc}')

    def _unpack(self, pos, format_specifier, length):
        start = pos + self._pos_wavedesc
        return np.frombuffer(self.data[start:start + length], self.endianness + format_specifier, count=1)[0]

    def _parse_string(self, pos, length=16):
        s = self._unpack(pos, "S{}".format(length), length)
        if sys.version_info > (3, 0):
            s = s.decode('ascii')
        return s

    def _parse_int16(self, pos):
        return self._unpack(pos, "u2", 2)

    def _parse_word(self, pos):
        return self._unpack(pos, "i2", 2)

    def _parse_int32(self, pos):
        return self._unpack(pos, "i4", 4)

    def _parse_float(self, pos):
        return self._unpack(pos, "f4", 4)

    def _parse_double(self, pos):
        return self._unpack(pos, "f8", 8)

    def _parse_byte(self, pos):
        return self._unpack(pos, "u1", 1)

    def _parse_timestamp(self, pos):
        second_float = self._parse_double(pos)
        second = int(second_float)
        microsecond = int((second_float - second) * 1e6)
        minute = self._parse_byte(pos + 8)
        hour = self._parse_byte(pos + 9)
        day = self._parse_byte(pos + 10)
        month = self._parse_byte(pos + 11)
        year = self._parse_word(pos + 12)

        return datetime(year, month, day, hour, minute, second, microsecond)

    def _parse_timebase(self, pos):
        timebase = self._parse_int16(pos)

        if timebase < 48:
            unit = "pnum k"[int(timebase / 9)]
            value = [1, 2, 5, 10, 20, 50, 100, 200, 500][timebase % 9]
            return "{} ".format(value) + unit.strip() + "s/div"
        elif timebase == 100:
            return "EXTERNAL"
