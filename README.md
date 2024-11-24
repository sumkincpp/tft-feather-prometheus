# TFT Feather Prometheus Exporter for BME680 and SCD41

This is a simple [CirtcuitPython](https://circuitpython.org/) project that reads data from a BME680 and SCD41 sensor and exposes the metrics data as prometheus endpoint.

- Board used: Adafruit Feather ESP32-S3 TFT with ESP32S3
- Sensors: BME680, SCD41

> Note: I had not checked what happens if you don't have display. I think it should work, but I'm not sure.

## Features

- Hot-pluggable I2C Sensors: remove or add sensors without restarting the service
- I2C Senso Auto-Discovery: every 360 seconds, the sensor list is re-discovered
- Watchdog timer: restarts after 15 seconds if freezes
- WiFi Auto-Reconnect (supervisor is reloaded)
- Sensor error detection
- Prometheus metrics
- Supported sensorts: BME680 (0x77), SCD4x (0x62)

TFT Display shows IP address, Temperature, Humidity and Pressure.

## Usage

Create `_secrets.py` with your WiFi credentials

```python
secrets = {
    'ssid' : 'XXXXX',
    'password' : 'YYYYY',
}
```

Create virtualenvironment and install `circup` (CircuitPython package manager)

> NOTE: Use [astral-sh/uv](https://github.com/astral-sh/uv) to create the virtual environment.
> NOTE: If you don't do this, you will certainly end up messing up your system python installation.

```bash
> uv venv --seed
> source .venv/bin/activate # Linux/macOS
> .venv\Scripts\activate # Windows
> pip install circup
```

Connect your esp32 and install dependencies to the board.

```bash
> circup install --auto
'adafruit_bitmap_font' is already installed.
'adafruit_bme680' is already installed.
'adafruit_bus_device' is already installed.
'adafruit_display_text' is already installed.
'adafruit_httpserver' is already installed.
'adafruit_ntp' is already installed.
'adafruit_scd4x' is already installed.
Installed 'adafruit_ticks'.
```

Copy the files to the board volume.

Linux/maOS X (Update the mount point before running!)

```bash
> cp -r *.py bmeTFT.bmp roundedHeavy-26.bdf /Volumes/CIRCUITPY/
```

Windows (Update the drive letter before running!)

```bash
> for %f in (*.py bmeTFT.bmp roundedHeavy-26.bdf) do copy %f D:\
```

If you develop the code, you can also install same packages to you virtual environment.

```bash
uv pip install -r requirements.txt
```

## Prometheus Metrics

### Example of sensor data

```
sensor_temperature_celsius{sensor_type="bme680"} 26.261
# HELP sensor_humidity_percent Relative humidity in percent
# TYPE sensor_humidity_percent gauge
sensor_humidity_percent{sensor_type="bme680"} 47.443
# HELP sensor_pressure_hpa Pressure in hectopascal
# TYPE sensor_pressure_hpa gauge
sensor_pressure_hpa{sensor_type="bme680"} 1010.372
# HELP sensor_gas_ohms Gas resistance in ohms
# TYPE sensor_gas_ohms gauge
sensor_gas_ohms{sensor_type="bme680"} 107925.000
# HELP last_measurement_time Last measurement time
# TYPE last_measurement_time gauge
last_measurement_time{sensor_type="bme680"} 22.990
# HELP sensor_co2_ppm CO2 in parts per million
# TYPE sensor_co2_ppm gauge
```

when failed

```
# HELP sensor_is_error Error reading sensor
# TYPE sensor_is_error gauge
sensor_is_error{sensor_type="bme680"} 1.000
# HELP last_measurement_time Last measurement time
# TYPE last_measurement_time gauge
last_measurement_time{sensor_type="bme680"} 84.529
```

## Links

Here are the links reformatted with descriptions:

* [uv](https://github.com/astral-sh/uv) - An extremely fast Python package installer and resolver
* [circup](https://github.com/adafruit/circup) - A command line tool for managing CircuitPython libraries
* [SCD4X Library Documentation](https://docs.circuitpython.org/projects/scd4x/en/latest/)
* [BME680 Library Documentation](https://docs.circuitpython.org/projects/bme680/en/latest/)
* [BME680 Library Source](https://github.com/adafruit/Adafruit_CircuitPython_BME680)
* [Adafruit SCD-40 and SCD-41](https://learn.adafruit.com/adafruit-scd-40-and-scd-41/python-circuitpython) - tutoria