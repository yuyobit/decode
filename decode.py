#!/usr/bin/env python

from __future__ import print_function
import argparse
from bulletin import processBulletin
import csv
import datetime
import glob
import re
import settings
import StringIO
import sys
import sqlite3
import yaml

# use NOAA bulletin separator line to split up bulletins
bulletinSeparator = '####[0-9]{9}####'

def main():

    parser = argparse.ArgumentParser(description='Parses NOAA TAC bulletins (SYNOP, METAR, TEMP).')
    parser.add_argument('stationInventory',
                        metavar='station-inventory',
                        help='CSV file containing station metadata')
    parser.add_argument('output',
                        metavar='output-file',
                        help='the output file where to write decoded data')
    parser.add_argument('input',
                        metavar='input-file',
                        help='the input file with bulletins')
    parser.add_argument('-v', '--verbose', dest='verbose',
                        help='print verbose output of filtering etc.',
                        action='store_true')
    parser.add_argument('-l', '--list', dest='filelist',
                        help='Specify that the input file contains a list with files to decode',
                        action='store_true')
    parser.add_argument('-t', '--type', dest='outputtype',
                        metavar='output-type',
                        help='Method of saving decoded data. One of csv (simple) and sqlite (full feature set). Defaults to sqlite.',
                        required=False,
                        default='sqlite')
    parser.add_argument('-f', '--filter', dest='filterfile',
                        metavar='filter-file',
                        help='YAML file specifying country and station filters',
                        required=False,
                        default=None)
    parser.add_argument('-d', '--date', dest='basedate',
                        metavar='base-date',
                        help='(yyyy-mm-dd) only day of month is encoded, so it is necessary to know which values belong to which month (and which year). Defaults to today.',
                        required=False,
                        default=datetime.date.today())
    args = parser.parse_args()

    for name, value in vars(args).items():
        setattr(settings, name, value)
    setattr(settings, 'decodedData', [])

    if settings.outputtype != 'csv' and settings.outputtype != 'sqlite':
        sys.exit('The specified output type is none of the allowed values csv or sqlite. Exiting.')

    if isinstance(settings.basedate, str):
        try:
            settings.basedate = datetime.datetime.strptime(settings.basedate, '%Y-%m-%d')
        except ValueError:
            sys.exit('The specified base date seems to be invalid. Exiting.')

    setupFilter()
    setupStationInventory()

    if settings.filelist:
        try:
            inputFile = open(settings.input, 'r')
            inputFiles = inputFile.readlines()
            inputFile.close()
            inputFiles = [x.strip('\n') for x in inputFiles]
        except IOError:
            sys.exit('Could not read input file list ' + settings.input + ', please check if it exists. Exiting.')
    else:
        inputFiles = glob.glob(settings.input)

    for inputFileName in inputFiles:
        print()
        print('Processing input file ' + inputFileName + '.')
        data = ''
        try:
            inputFile = open(inputFileName, 'r')
            data = inputFile.read()
            inputFile.close()
            # convert newlines into spaces and remove carriage returns
            data = data.replace('\n', ' ')
            data = data.replace('\r', '')
            # collapse spaces
            data = ' '.join(data.split())
        except IOError:
            sys.exit('Could not read input file ' + inputFileName + ', please check if it exists. Exiting.')

        # specify regular expression of what separates bulletins in the text file
        bulletins = re.split(bulletinSeparator, data)

        count = 0
        for bulletin in bulletins:
            bulletin = bulletin.strip()
            # first one will be usually empty
            if len(bulletin) == 0:
                continue
            count += 1
            processBulletin(bulletin, count, settings.basedate)

    if settings.outputtype == 'csv':
        writeCsvOutput()
    elif settings.outputtype == 'sqlite':
        writeSqliteOutput()

def setupFilter():
    stationList = []
    countryList = None

    if settings.filterfile:
        filterSpec = None
        try:
            filterFile = open(settings.filterfile, 'r')
            filterSpec = yaml.safe_load(filterFile.read())
            filterFile.close()
        except IOError:
            sys.exit('Could not read filter file, please check if it exists. Exiting.')

        if 'countries' in filterSpec:
            countryList = ''
            for country in filterSpec['countries']:
                countryList += country + '|'
            countryList = countryList[:len(countryList) - 1]
        else:
            countryList = '[A-Z]{2}'

        if 'stations' in filterSpec and 'synop' in filterSpec['stations']:
            stationList = filterSpec['stations']['synop']
    else:
        countryList = '[A-Z]{2}'

    setattr(settings, 'stationList', stationList)
    setattr(settings, 'countryList', countryList)

def setupStationInventory():
    stationInventory = {}
    try:
        stationFile = open(settings.stationInventory, 'r')
        stations = unicode(stationFile.read(), 'utf-8')
        stationFile.close()
        reader = csv.DictReader(StringIO.StringIO(stations.encode('utf-8')),
            quoting=csv.QUOTE_ALL, delimiter=',')
        for row in reader:
            stationInventory[row['wmo']] = row
    except IOError:
        sys.exit('Could not read station inventory file, please check if it exists. Exiting.')

    setattr(settings, 'stationInventory', stationInventory)

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
            correctionSeq = result[14]
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
            amendmentSeq = result[15]
            cursor.execute('DELETE FROM synop WHERE wmo = ? AND timestamp = ?', idTuple)
            cursor.execute('INSERT INTO synop VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                (correction['station_id'], correction['timestamp'], correction['temperature'], correction['dew_point_temperature'],
                    correction['rel_humidity'], correction['wind_direction'], correction['wind_speed'],
                    correction['gust_speed'], correction['station_pressure'], correction['pressure'],
                    correction['cloud_cover'], correction['sun_duration'], correction['current_weather'], correction['snow_depth'],
                    correction['modifier']['sequence'], amendmentSeq))
    connection.commit()

    connection.close()

if __name__ == "__main__":
    main()
