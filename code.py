# type: ignore
import os
import time

import adafruit_bme680
import adafruit_ntp
import adafruit_scd4x

# import json
# import simpleio
# import vectorio
import board
import displayio
import microcontroller
import rtc
import socketpool
import supervisor
import terminalio
import wifi
from adafruit_bitmap_font import bitmap_font
from adafruit_display_text import bitmap_label, wrap_text_to_lines
from adafruit_httpserver import Request, Response, Server
from microcontroller import watchdog as w
from watchdog import WatchDogMode

from _secrets import secrets

w.timeout = 15  # Set a timeout of 15 seconds
w.mode = WatchDogMode.RESET  # Set the mode to reset the device

# When running on esp32, the typing module is not available
try:
    from typing import Dict, List, Optional, Tuple
except ImportError:
    pass

# dataclasses are not supported xD
# import dataclasses


TZ_OFFSET = 1  # UTC+1


def connect_wifi(ssid: str, password: str) -> "Tuple[socketpool.SocketPool, adafruit_ntp.NTP]":
    print("Connecting to WiFi...")

    while True:
        try:
            wifi.radio.connect(ssid, password)
        except (Exception, RuntimeError) as e:
            print("Error connecting to WiFi", str(e))
            time.sleep(3)
            continue
        break

    print("Connected to WiFi!")

    #  ntp clock - update tz_offset to your timezone
    pool = socketpool.SocketPool(wifi.radio)
    ntp = adafruit_ntp.NTP(pool, tz_offset=TZ_OFFSET)
    rtc.RTC().datetime = ntp.datetime

    if time.localtime().tm_year < 2022:
        print("Setting System Time in UTC")
        rtc.RTC().datetime = ntp.datetime
    else:
        print("Year seems good, skipping set time.")

    return (pool, ntp)


class TempHumidityDisplay:
    def __init__(self) -> None:
        self.display = board.DISPLAY

        self.temp_format = "%0.1f° C"
        self.humidity_format = "%0.1f %%"
        self.pressure_format = "%0.2f"

        #  bitmap font
        font_file = "/roundedHeavy-26.bdf"
        font = bitmap_font.load_font(font_file)

        #  text elements
        self.temp_text = bitmap_label.Label(font, text="", x=20, y=80, color=0xFFFFFF)
        self.humid_text = bitmap_label.Label(font, text="", x=95, y=80, color=0xFFFFFF)
        self.press_text = bitmap_label.Label(font, text="", x=170, y=80, color=0xFFFFFF)

        self.ip_address_text = bitmap_label.Label(terminalio.FONT, text="", x=12, y=105, color=0xFFFFFF)

        self.time_text = bitmap_label.Label(terminalio.FONT, text="", x=125, y=105, color=0xFFFFFF)

    def update_time(self, datetime=None) -> None:
        now = time.localtime()
        # if datetime is None:
        #     datetime = now
        # year, mon, day, hour, minute, seconds, *_ = datetime
        year, mon, day, hour, minute, seconds, *_ = now
        clock_view = "%02d:%02d:%02d" % (hour, minute, seconds)

        self.time_text.text = "\n".join(wrap_text_to_lines("Last update %s/%s/%s %s" % (mon, day, year, clock_view), 20))

    def update_ip_address(self, ip_address) -> None:
        self.ip_address_text.text = ip_address

    def init(self) -> None:
        #  load bitmap
        bitmap = displayio.OnDiskBitmap("/bmeTFT.bmp")
        tile_grid = displayio.TileGrid(bitmap, pixel_shader=bitmap.pixel_shader)
        group = displayio.Group()
        group.append(tile_grid)

        group.append(self.ip_address_text)
        group.append(self.temp_text)
        group.append(self.humid_text)
        group.append(self.press_text)
        group.append(self.time_text)

        if self.display:
            # Ok, if we have a display, let's assign the group to it
            self.display.root_group = group

    def update(self, temp, humidity, pressure) -> None:
        self.temp_text.text = self.temp_format % temp
        self.humid_text.text = self.humidity_format % humidity
        self.press_text.text = self.pressure_format % pressure

    def update_bme680(self, bme680: Optional[adafruit_bme680.Adafruit_BME680_I2C]) -> None:
        if not bme680:
            return

        self.temp_text.text = self.temp_format % bme680.temperature
        self.humid_text.text = self.humidity_format % bme680.relative_humidity
        self.press_text.text = self.pressure_format % bme680.pressure

    def update_scd4x(self, scd4x: Optional[adafruit_scd4x.SCD4X]) -> None:
        if not scd4x:
            return

        self.temp_text.text = self.temp_format % scd4x.temperature
        self.humid_text.text = self.humidity_format % scd4x.relative_humidity


class SensorMetric:
    def __init__(
        self,
        name: str,
        description: str,
        type: str,
        value: float,
        labels: "Optional[Dict]" = None,
    ) -> None:
        self.name = name
        self.description = description
        self.type = type
        self.value = value

        self.labels = labels if labels else {}

    def __repr__(self) -> str:
        return f"SensorMetric({self.name}, {self.description}, {self.type}, {self.value}, {self.labels})"


class I2CSensorsManager:
    def __init__(self) -> None:
        self.init()

    def init(self) -> None:
        # i2c = board.I2C()  # uses board.SCL and board.SDA
        # i2c = board.STEMMA_I2C()  # For using the built-in STEMMA QT connector on a microcontroller
        self._i2c = board.STEMMA_I2C()

        # we assume there are only two sensors
        self.init_bme680()  # 0x77
        self.init_scd4x()  # 0x62

        self._bme680_last_measurement_time = 0
        self._scd4x_metrics = []

    def deinit(self) -> None:
        self._i2c.deinit()
        self._i2c = None
        self.bme680 = None
        self.scd4x = None

    @property
    def i2c(self) -> "board.I2C":
        return self._i2c

    def init_bme680(self) -> None:
        try:
            self.bme680 = adafruit_bme680.Adafruit_BME680_I2C(self.i2c, debug=False)
            # change this to match the location's pressure (hPa) at sea level
            self.bme680.sea_level_pressure = 1013.25
        except Exception as e:
            self.bme680 = None
            print("Error initializing BME680", str(e))

    def init_scd4x(self) -> None:
        try:
            self.scd4x = adafruit_scd4x.SCD4X(self.i2c)
            # we should read serial before starting the periodic measurement
            value = self.scd4x.serial_number
            # "0x" + "".join([hex(x) for x in self.scd4x_serial_number])
            if isinstance(value, str):
                self.scd4x_serial_number = value
            else:
                self.scd4x_serial_number = "0x" + "".join([f"{v:x}" for v in value])

            self.scd4x.start_periodic_measurement()
        except Exception as e:
            self.scd4x = None
            self.scd4x_serial_number = ""
            print("Error initializing SCD4X", str(e))

    def read_bme680(self) -> "List[SensorMetric]":
        sensor = self.bme680

        if not sensor:
            return []

        try:
            self._bme680_last_measurement_time = time.monotonic()
            self._bme680_metrics = [
                SensorMetric("sensor_temperature_celsius", "Temperature in Celsius", "gauge", sensor.temperature),
                SensorMetric("sensor_humidity_percent", "Relative humidity in percent", "gauge", sensor.relative_humidity),
                SensorMetric("sensor_pressure_hpa", "Pressure in hectopascal", "gauge", sensor.pressure),
                SensorMetric("sensor_gas_ohms", "Gas resistance in ohms", "gauge", sensor.gas),
                # last measurement time
                SensorMetric("last_measurement_time", "Last measurement time", "gauge", self._bme680_last_measurement_time),
                # sensor_info
                SensorMetric("sensor_info", "Sensor info", "gauge", 1, labels={"sensor_name": "BME680"}),
            ]
            metrics = self._bme680_metrics
        except (Exception, RuntimeError) as e:
            print("Error reading BME680", str(e))
            metrics = [m for m in getattr(self, "_bme680_metrics", [])]

            metrics.append(SensorMetric("sensor_is_error", f"Error: {e}", "gauge", 1))

        for metric in metrics:
            metric.labels["sensor_type"] = "bme680"

        return metrics

    def read_scd4x(self) -> "List[SensorMetric]":
        """
        SC4DX sensor metrics are not very stable, so when we read the sensor data, runtime errors can occur.
        Because of that we cache the last metrics and return them in case of an error.
        """

        sensor = self.scd4x

        if not sensor:
            return []

        try:
            if sensor.data_ready:
                sensor_info_labels = {
                    "sensor_name": "SCD4X",
                    "serial_number": self.scd4x_serial_number,
                }

                metrics = [
                    SensorMetric("sensor_co2_ppm", "CO2 in parts per million", "gauge", sensor.CO2),
                    SensorMetric("sensor_temperature_celsius", "Temperature in Celsius", "gauge", sensor.temperature),
                    SensorMetric("sensor_humidity_percent", "Relative humidity in percent", "gauge", sensor.relative_humidity),
                    # last measurement time
                    SensorMetric("last_measurement_time", "Last measurement time", "gauge", time.monotonic()),
                    # sensor_info
                    SensorMetric("sensor_info", "Sensor info", "gauge", 1, labels=sensor_info_labels),
                ]

                self._scd4x_metrics = metrics
            else:
                metrics = getattr(self, "_scd4x_metrics", [])
        except (Exception, RuntimeError) as e:
            print("Error reading SCD4X", str(e))
            metrics = [m for m in getattr(self, "_scd4x_metrics", [])]

            metrics.append(SensorMetric("sensor_is_error", f"Error: {e}", "gauge", 1))

        for metric in metrics:
            metric.labels["sensor_type"] = "scd4x"

        return metrics

    def read_metrics(self) -> "List[SensorMetric]":
        metrics = []

        metrics.extend(self.read_bme680())
        metrics.extend(self.read_scd4x())

        return metrics


i2c_sm = I2CSensorsManager()


pool, ntp = connect_wifi(secrets["ssid"], secrets["password"])
server = Server(pool, debug=True)

last_discovery_time = time.monotonic()
last_screen_update_time = time.monotonic()


@server.route("/metrics", append_slash=True)
def metrics_handler(request: Request) -> Response:
    print("Received request for metrics")

    response_text = ""

    start_time = time.monotonic()

    metrics = i2c_sm.read_metrics()

    for metric in metrics:
        response_text += "# HELP %s %s\n" % (metric.name, metric.description)
        response_text += "# TYPE %s %s\n" % (metric.name, metric.type)
        labels = ", ".join([f'{k}="{v}"' for k, v in metric.labels.items()])
        response_text += "%s{%s} %0.3f\n" % (metric.name, labels, metric.value)

    measurement_time = time.monotonic() - start_time

    response_text += "# HELP microcontroller_measurement_time_seconds Time to measure metrics in seconds\n"
    response_text += "# TYPE microcontroller_measurement_time_seconds gauge\n"
    response_text += "microcontroller_measurement_time_seconds %0.3f\n" % measurement_time

    if hasattr(microcontroller, "cpus"):
        cpus = microcontroller.cpus
    else:
        cpus = [microcontroller.cpu]

    for cpu_id, cpu in enumerate(cpus):
        response_text += "# HELP microcontroller_cpu_temperature_celsius TemperatuPre in Celsius\n"
        response_text += "# TYPE microcontroller_cpu_temperature_celsius gauge\n"
        response_text += 'microcontroller_cpu_temperature_celsius{cpu="%s"} %0.1f\n' % (cpu_id, cpu.temperature)

        response_text += "# HELP microcontroller_cpu_frequency_hz Frequency in hertz\n"
        response_text += "# TYPE microcontroller_cpu_frequency_hz gauge\n"
        response_text += 'microcontroller_cpu_frequency_hz{cpu="%s"} %d\n' % (cpu_id, cpu.frequency)

    response_text += "# HELP microcontroller_last_discovery_time_seconds Last discovery time in seconds\n"
    response_text += "# TYPE microcontroller_last_discovery_time_seconds gauge\n"
    response_text += "microcontroller_last_discovery_time_seconds %0.3f\n" % last_discovery_time

    response_text += "# HELP microcontroller_next_discovery_time_seconds Next discovery time in seconds\n"
    response_text += "# TYPE microcontroller_next_discovery_time_seconds gauge\n"
    response_text += "microcontroller_next_discovery_time_seconds %0.3f\n" % (DISCOVERY_PERIOD - (time.monotonic() - last_discovery_time))

    response_text += "# HELP microcontroller_last_screen_update_time_seconds Last screen update time in seconds\n"
    response_text += "# TYPE microcontroller_last_screen_update_time_seconds gauge\n"
    response_text += "microcontroller_last_screen_update_time_seconds %0.3f\n" % last_screen_update_time

    # microcontroller_info

    try:
        info_labels = {
            "cpu_frequency": microcontroller.cpu.frequency,
            "board_id": os.uname().machine,
            "board_name": board.board_id,
            "nvm_bytes_count": len(microcontroller.nvm),
        }
    except AttributeError:
        raise
        # info_labels = {}
        # pass

    info_labels_str = ", ".join([f'{k}="{v}"' for k, v in info_labels.items()])

    response_text += "# HELP microcontroller_info Microcontroller info\n"
    response_text += "# TYPE microcontroller_info gauge\n"
    response_text += "microcontroller_info{%s} 1\n" % info_labels_str

    return Response(request, response_text)


#  initialize display
temp_humidity_display = TempHumidityDisplay()
temp_humidity_display.init()
temp_humidity_display.update_ip_address(str(wifi.radio.ipv4_address))

MAIN_LOOP_DELAY = 0.1

# clocks to countdown
DISPLAY_UPDATE_INTERVAL = 10  # seconds
# period to rediscover i2c devices
DISCOVERY_PERIOD = 360  # seconds

server.start(str(wifi.radio.ipv4_address))

while True:
    current_time = time.monotonic()
    if current_time - last_discovery_time > DISCOVERY_PERIOD:
        i2c_sm.deinit()
        i2c_sm.init()

        last_discovery_time = current_time

    try:
        pool_result = server.poll()
        if pool_result is not None:
            print("pool_result", pool_result)

    except OSError as e:
        print("pool_result error", e)

    if current_time - last_screen_update_time > DISPLAY_UPDATE_INTERVAL:
        try:
            if i2c_sm.bme680:
                temp_humidity_display.update_bme680(i2c_sm.bme680)
            elif i2c_sm.scd4x:
                temp_humidity_display.update_scd4x(i2c_sm.scd4x)
        except (Exception, RuntimeError):
            pass

        try:
            temp_humidity_display.update_time()
        # pylint: disable=broad-except
        except (ValueError, RuntimeError, OSError, ConnectionError) as e:
            #  if something disrupts the loop, reconnect
            print("Network error, reconnecting\n", str(e))
            supervisor.reload()
            continue

        last_screen_update_time = current_time

    time.sleep(MAIN_LOOP_DELAY)
    w.feed()
