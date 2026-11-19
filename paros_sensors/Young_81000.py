import os
import influxdb_client
from ParosSerialSensor import ParosSerialSensor
from ParosSensor import ParosSensor
import serial
import argparse
import socket
import pathlib
import logging
import math


# Wire order for CUSTOM 789AB and 789AB5, respectively. InfluxDB stores
# named fields, so its serialized field order need not match wire order.
LEGACY_COLUMNS = (
    "speed_3d", "azimuth", "elevation", "speed_of_sound", "sonic_temperature",
)
UVW_COLUMNS = LEGACY_COLUMNS + ("u", "v", "w")


def parse_sample(line):
    """Parse a complete CR-terminated CUSTOM 789AB or 789AB5 record.

    Missing UVW remains absent for legacy sensors; never manufacture zeros.
    Values are sensor-native (PCAR uses m/s and degrees Celsius).
    Numeric validity does not establish acoustic measurement quality.
    """
    if not isinstance(line, str) or not line.endswith('\r'):
        raise ValueError("Incomplete sonic record")
    parts = line.split()
    if len(parts) not in (len(LEGACY_COLUMNS), len(UVW_COLUMNS)):
        raise ValueError("Expected 5 (789AB) or 8 (789AB5) values")
    values = tuple(float(part) for part in parts)
    if not all(math.isfinite(value) for value in values):
        raise ValueError("Non-finite sonic value")
    return dict(zip(UVW_COLUMNS, values))


class Young_81000(ParosSerialSensor):
    def __init__(self, box_id, sensor_id, data_loc, device_file):
        super().__init__(
            box_id,
            sensor_id,
            data_loc,
            device_file,
            ser_baud=38400,
            ser_bytesize=serial.EIGHTBITS,
            ser_parity=serial.PARITY_NONE,
            ser_stopbits=serial.STOPBITS_ONE,
            ser_timeout=1.0
        )

        self.box_id = box_id
        logging.info(f"Starting RM Young 81000 sampler for sensor id {sensor_id}")

    def samplingLoop(self):
        fail_count = 0

        while True:
            try:
                if fail_count > 10:
                    logging.critical("Stopping due to too many data failures")
                    exit(1)

                strIn = super().readSerial(b'\r')

                try:
                    fields = parse_sample(strIn)
                except ValueError as exc:
                    fail_count += 1
                    logging.warning("Invalid RM Young 81000 record (%s/11): %s", fail_count, exc)
                    continue

                fail_count = 0

                p = influxdb_client.Point(self.box_id)
                for name, value in fields.items():
                    p.field(name, value)

                ParosSensor.addSample(self, p)

            except KeyboardInterrupt:
                logging.info("Stopping sampling...")
                exit(0)


if __name__ == "__main__":
    from dotenv import load_dotenv

    logging.basicConfig(level=logging.INFO)

    file_path = pathlib.Path(__file__).parent.resolve()
    load_dotenv(f"{file_path}/../.env")

    if os.getenv("PAROS_DATA_LOCATION") is None:
        logging.critical("Unable to find environment variable PAROS_DATA_LOCATION. Does .env exist?")
        exit(1)

    parser = argparse.ArgumentParser()
    parser.add_argument("sensor_id", help="Sensor ID Number", type=str)
    parser.add_argument("device", help="Device file for serial connection", type=str)
    args = parser.parse_args()

    cur_sensor = Young_81000(
        socket.gethostname(),
        args.sensor_id,
        os.getenv("PAROS_DATA_LOCATION"),
        args.device
    )
    cur_sensor.samplingLoop()
