import csv
import datetime
import settings
import sqlite3

# CSV output provides a simple dumping of decoded values
# advanced functions like correcting data according to bulletin modifiers will not be done
# as the CSV file is newly created every time
# also station information is not saved in the CSV file
def writeCsvOutput():
    try:
        print()
        print('Writing to CSV output file ' + settings.output + '...')
        outputFile = open(settings.output, 'w')
        writer = csv.DictWriter(outputFile, fieldnames=['bulletin_id', 'bulletin_issuer', 'station_id',
            'timestamp', 'modifier_type', 'modifier_sequence', 'temperature', 'dew_point_temperature',
            'rel_humidity', 'wind_direction', 'wind_speed', 'gust_speed', 'station_pressure', 'pressure',
            'cloud_cover', 'sun_duration', 'precipitation_amount', 'precipitation_duration', 'current_weather', 'snow_depth'],
            quoting=csv.QUOTE_ALL, delimiter=',')

        writer.writeheader()
        for dataRow in settings.decodedData:
            if dataRow['modifier'] != None:
                dataRow['modifier_type'] = dataRow['modifier']['type']
                dataRow['modifier_sequence'] = dataRow['modifier']['sequence']
            else:
                dataRow['modifier_type'] = None
                dataRow['modifier_sequence'] = None
            del dataRow['modifier']

            if dataRow['precipitation'] != None:
                # not possible to write more than one precipitation entry to CSV
                for precip in dataRow['precipitation']:
                    if precip != None:
                        dataRow['precipitation_amount'] = precip['amount']
                        dataRow['precipitation_duration'] = precip['duration']
                    break
            else:
                dataRow['precipitation_amount'] = None
                dataRow['precipitation_duration'] = None
            del dataRow['precipitation']

            writer.writerow(dataRow)
    except IOError:
        sys.exit('Could not open output file. Exiting.')

def writeSqliteOutput():
    print()
    print('Writing to Sqlite output container ' + settings.output + '...')
    connection = sqlite3.connect(settings.output)
    cursor = connection.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS station (
            wmo INTEGER PRIMARY KEY,
            icao TEXT,
            lat REAL,
            lon REAL,
            ele REAL,
            name TEXT,
            int_name TEXT)
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS synop_daily (
            wmo INTEGER,
            date TEXT,
            min_temperature REAL,
            max_temperature REAL,
            precipitation REAL,
            sun_duration REAL,
            correction_sequence TEXT,
            amendment_sequence TEXT,
            PRIMARY KEY(wmo, date))
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS synop (
            wmo INTEGER,
            timestamp TEXT,
            temperature REAL,
            dew_point_temperature REAL,
            rel_humidity REAL,
            wind_direction INTEGER,
            wind_speed REAL,
            gust_speed REAL,
            station_pressure REAL,
            pressure REAL,
            cloud_cover INTEGER,
            sun_duration REAL,
            current_weather INTEGER,
            snow_depth REAL,
            correction_sequence TEXT,
            amendment_sequence TEXT,
            PRIMARY KEY(wmo, timestamp))
    ''')
    # todo precipitation
    connection.commit()

    stations = []
    synop = []
    for dataRow in settings.decodedData:
        station = settings.stationInventory[dataRow['station_id']]
        # make sure station ends up in list only once
        duplicates = filter(lambda data: data[0] == dataRow['station_id'], stations)
        if len(duplicates) == 0:
            stations.append((station['wmo'], unicode(station['icao'], 'utf-8'),
                station['lat'], station['lon'], station['ele'],
                unicode(station['name'], 'utf-8'), unicode(station['int_name'], 'utf-8')))

        # deal with amendments and corrections later
        if dataRow['modifier'] == None or (dataRow['modifier']['type'] != 'AA' and dataRow['modifier']['type'] != 'CC'):
            synop.append((dataRow['station_id'], dataRow['timestamp'], dataRow['temperature'], dataRow['dew_point_temperature'],
                dataRow['rel_humidity'], dataRow['wind_direction'], dataRow['wind_speed'],
                dataRow['gust_speed'], dataRow['station_pressure'], dataRow['pressure'],
                dataRow['cloud_cover'], dataRow['sun_duration'], dataRow['current_weather'], dataRow['snow_depth'],
                '', ''))

            if dataRow['daily_precipitation'] != None:
                if dataRow['timestamp'].hour >= 0 and dataRow['timestamp'].hour < 12:
                    date = dataRow['timestamp'] - datetime.timedelta(days=1)
                else:
                    date = dataRow['timestamp']
                station = dataRow['station_id']
                cursor.execute('SELECT * FROM synop_daily WHERE wmo = ? AND date = ?', (station, date.strftime("%Y-%m-%d")))
                if cursor.fetchone() != None:
                    cursor.execute('UPDATE synop_daily SET precipitation = ? WHERE wmo = ? AND date = ?',
                        (dataRow['daily_precipitation'], station, date.strftime("%Y-%m-%d")))
                else:
                    cursor.execute('INSERT INTO synop_daily VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                        (station, date.strftime("%Y-%m-%d"), None, None, dataRow['daily_precipitation'], None, '', ''))
                connection.commit()

            if dataRow['daily_sun_duration'] != None:
                date = dataRow['timestamp'] - datetime.timedelta(days=1)
                station = dataRow['station_id']
                cursor.execute('SELECT * FROM synop_daily WHERE wmo = ? AND date = ?', (station, date.strftime("%Y-%m-%d")))
                if cursor.fetchone() != None:
                    cursor.execute('UPDATE synop_daily SET sun_duration = ? WHERE wmo = ? AND date = ?',
                        (dataRow['daily_sun_duration'], station, date.strftime("%Y-%m-%d")))
                else:
                    cursor.execute('INSERT INTO synop_daily VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                        (station, date.strftime("%Y-%m-%d"), None, None, None, dataRow['daily_sun_duration'], '', ''))
                connection.commit()

    # IGNORE means that it does not fail if the key already exists
    cursor.executemany('INSERT OR IGNORE INTO station VALUES (?, ?, ?, ?, ?, ?, ?)', stations)
    cursor.executemany('INSERT OR IGNORE INTO synop VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)', synop)
    connection.commit()

    amendments = filter(lambda data: data['modifier'] != None and data['modifier']['type'] == 'AA', settings.decodedData)

    for amendment in amendments:
        idTuple = (correction['station_id'], correction['timestamp'])
        cursor.execute('SELECT * FROM synop WHERE wmo = ? AND timestamp = ?', idTuple)
        result = cursor.fetchone()
        # insert only if data is either not in the DB
        # or the amendment sequence is not present (i.e. has not been amended so far)
        # or the amendment sequence is lower (i.e. our amendment is newer)
        if result == None or result[15] == None or result[15] < correction['modifier']['sequence']:
            if result != None:
                correctionSeq = result[14]
            else:
                correctionSeq = ''
            cursor.execute('DELETE FROM synop WHERE wmo = ? AND timestamp = ?', idTuple)
            cursor.execute('INSERT INTO synop VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                (amendment['station_id'], amendment['timestamp'], amendment['temperature'], amendment['dew_point_temperature'],
                    amendment['rel_humidity'], amendment['wind_direction'], amendment['wind_speed'],
                    amendment['gust_speed'], amendment['station_pressure'], amendment['pressure'],
                    amendment['cloud_cover'], amendment['sun_duration'], amendment['current_weather'], amendment['snow_depth'],
                    amendmentSeq, amendment['modifier']['sequence']))
    connection.commit()

    corrections = filter(lambda data: data['modifier'] != None and data['modifier']['type'] == 'CC', settings.decodedData)

    for correction in corrections:
        idTuple = (correction['station_id'], correction['timestamp'])
        cursor.execute('SELECT * FROM synop WHERE wmo = ? AND timestamp = ?', idTuple)
        result = cursor.fetchone()
        # insert only if data is either not in the DB
        # or the correction sequence is not present (i.e. has not been corrected so far)
        # or the correction sequence is lower (i.e. our correction is newer)
        if result == None or result[14] == None or result[14] < correction['modifier']['sequence']:
            if result != None:
                amendmentSeq = result[15]
            else:
                amendmentSeq = ''
            cursor.execute('DELETE FROM synop WHERE wmo = ? AND timestamp = ?', idTuple)
            cursor.execute('INSERT INTO synop VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                (correction['station_id'], correction['timestamp'], correction['temperature'], correction['dew_point_temperature'],
                    correction['rel_humidity'], correction['wind_direction'], correction['wind_speed'],
                    correction['gust_speed'], correction['station_pressure'], correction['pressure'],
                    correction['cloud_cover'], correction['sun_duration'], correction['current_weather'], correction['snow_depth'],
                    correction['modifier']['sequence'], amendmentSeq))
    connection.commit()

    connection.close()
