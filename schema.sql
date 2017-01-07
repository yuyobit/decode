CREATE TABLE IF NOT EXISTS station (
    id INTEGER PRIMARY KEY,
    wmo INTEGER UNIQUE,
    icao TEXT UNIQUE,
    country TEXT, -- ISO 3166-1 alpha-2
    lat REAL,
    lon REAL,
    ele REAL,
    name TEXT,
    int_name TEXT
)

CREATE TABLE IF NOT EXISTS basic (
    station_id INTEGER,
    timestamp TEXT,
    temperature REAL,
    dew_point_temperature REAL,
    rel_humidity REAL,
    wind_direction INTEGER,
    wind_speed REAL,
    station_pressure REAL,
    pressure REAL,
    sun_duration REAL,
    correction_sequence TEXT,
    amendment_sequence TEXT,
    PRIMARY KEY(station_id, timestamp),
    FOREIGN KEY(station_id) REFERENCES station(id)
)

CREATE TABLE IF NOT EXISTS precipitation (
    station_id INTEGER,
    from TEXT,
    to TEXT,
    amount REAL,
    correction_sequence TEXT,
    amendment_sequence TEXT,
    PRIMARY KEY(station_id, from, to),
    FOREIGN KEY(station_id) REFERENCES station(id)
)

CREATE TABLE IF NOT EXISTS gust (
    station_id INTEGER,
    timestamp TEXT,
    gust_speed REAL,
    PRIMARY KEY(station_id, timestamp),
    FOREIGN KEY(station_id) REFERENCES station(id)
)

CREATE TABLE IF NOT EXISTS snow (
    station_id INTEGER,
    timestamp TEXT,
    snow_depth REAL,
    PRIMARY KEY(station_id, timestamp),
    FOREIGN KEY(station_id) REFERENCES station(id)
)

CREATE TABLE IF NOT EXISTS weather (
    station_id INTEGER,
    timestamp TEXT,
    current_weather REAL,
    PRIMARY KEY(station_id, timestamp),
    FOREIGN KEY(station_id) REFERENCES station(id)
)

CREATE TABLE IF NOT EXISTS cloud (
    station_id INTEGER,
    timestamp TEXT,
    cloud_cover INTEGER,
    PRIMARY KEY(station_id, timestamp),
    FOREIGN KEY(station_id) REFERENCES station(id)
)

CREATE TABLE IF NOT EXISTS synop_daily (
    wmo INTEGER,
    date TEXT,
    min_temperature REAL,
    max_temperature REAL,
    sun_duration REAL,
    correction_sequence TEXT,
    amendment_sequence TEXT,
    PRIMARY KEY(wmo, date))
