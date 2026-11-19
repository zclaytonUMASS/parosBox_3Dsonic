"""Offline regression tests: real InfluxDB serialization, mocked serial input."""
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'paros_sensors'))
from Young_81000 import LEGACY_COLUMNS, UVW_COLUMNS, Young_81000, parse_sample
from ParosSerialSensor import ParosSerialSensor
from ParosSensor import ParosSensor

LEGACY = '5.00 36.9 0.0 343.20 20.10\r'
EXTENDED = '5.00 36.9 0.0 343.20 20.10 -3.00 +4.00 -0.00\r'


class SonicTests(unittest.TestCase):
    def test_legacy_has_no_fabricated_components(self):
        self.assertEqual(parse_sample(LEGACY), dict(zip(LEGACY_COLUMNS, (5., 36.9, 0., 343.2, 20.1))))

    def test_extended_order_and_signed_components(self):
        self.assertEqual(parse_sample(EXTENDED), dict(zip(UVW_COLUMNS, (5., 36.9, 0., 343.2, 20.1, -3., 4., -0.))))

    def test_whitespace_and_crlf_residue(self):
        self.assertEqual(parse_sample('\n\t  ' + EXTENDED.replace(' ', '  \t')), parse_sample(EXTENDED))

    def test_wrong_widths(self):
        for count in (0, 1, 4, 6, 7, 9, 10):
            with self.subTest(count=count), self.assertRaises(ValueError):
                parse_sample(' '.join(['1'] * count) + '\r')

    def test_bad_numbers_in_every_column(self):
        for column in range(8):
            for bad in ('nan', 'NaN', 'inf', '-inf', '1e999', '***', 'ERR'):
                parts = EXTENDED.split()
                parts[column] = bad
                with self.subTest(column=column, bad=bad), self.assertRaises(ValueError):
                    parse_sample(' '.join(parts) + '\r')

    def test_timeouts_and_truncated_records(self):
        for line in (None, '', '\r', LEGACY[:-1], EXTENDED[:-1], LEGACY.rstrip('\r') + '\n'):
            with self.subTest(line=line), self.assertRaises(ValueError):
                parse_sample(line)

    def test_menu_text_and_polled_prefix_rejected(self):
        for line in ('COMMANDS (VERSION 7.0.01)\r', '789AB5\r', 'A ' + EXTENDED):
            with self.subTest(line=line), self.assertRaises(ValueError):
                parse_sample(line)

    def run_stream(self, records):
        sensor = Young_81000.__new__(Young_81000)
        sensor.box_id = 'offline-test'
        with patch.object(ParosSerialSensor, 'readSerial', side_effect=records + [KeyboardInterrupt]) as reader, \
             patch.object(ParosSensor, 'addSample') as writer:
            with self.assertRaises(SystemExit) as stopped:
                sensor.samplingLoop()
            self.assertEqual(stopped.exception.code, 0)
            self.assertTrue(all(call.args == (b'\r',) for call in reader.call_args_list))
            return [call.args[1].to_line_protocol() for call in writer.call_args_list]

    def test_rollout_and_rollback_have_no_stale_uvw(self):
        points = self.run_stream([LEGACY, EXTENDED, LEGACY])
        self.assertEqual(len(points), 3)
        for point in (points[0], points[2]):
            self.assertNotIn(',u=', point)
        self.assertIn(',u=-3', points[1])
        self.assertIn(',v=4', points[1])
        self.assertIn(',w=-0', points[1])
        self.assertIn('sonic_temperature=20.1', points[1])

    def test_invalid_records_are_skipped_and_good_record_resets_failures(self):
        self.assertEqual(len(self.run_stream([None] * 10 + [EXTENDED] + ['bad\r'] * 10 + [LEGACY])), 2)

    def test_eleven_consecutive_failures_exit(self):
        sensor = Young_81000.__new__(Young_81000)
        with patch.object(ParosSerialSensor, 'readSerial', return_value=None), \
             patch.object(ParosSensor, 'addSample') as writer:
            with self.assertRaises(SystemExit) as stopped:
                sensor.samplingLoop()
            self.assertEqual(stopped.exception.code, 1)
            writer.assert_not_called()

    def test_serial_settings_and_no_configuration_writes(self):
        with tempfile.TemporaryDirectory() as data, patch('ParosSerialSensor.serial.Serial') as serial_class:
            serial_class.return_value.isOpen.return_value = False
            Young_81000('offline-test', 'sonic', data, '/dev/fake-sonic')
            port = serial_class.return_value
            self.assertEqual((port.baudrate, port.bytesize, port.parity, port.stopbits), (38400, 8, 'N', 1))
            port.write.assert_not_called()

    def test_real_local_file_contains_named_fields_and_metadata(self):
        import influxdb_client
        with tempfile.TemporaryDirectory() as data:
            sensor = ParosSensor('offline-test', 'sonic', data)
            point = influxdb_client.Point('offline-test')
            for name, value in parse_sample(EXTENDED).items():
                point.field(name, value)
            sensor.addSample(point)
            files = list((pathlib.Path(data) / 'sonic').iterdir())
            self.assertEqual(len(files), 1)
            record = files[0].read_text()
            self.assertTrue(record.startswith('offline-test,id=sonic '))
            for name in UVW_COLUMNS:
                self.assertIn(name + '=', record)
            self.assertTrue(record.split()[-1].isdigit())


if __name__ == '__main__':
    unittest.main()
