#!/usr/bin/env python

from __future__ import print_function
import argparse
import csv
import datetime
import math
import re
import sys
import StringIO
import yaml

stationList = []
countryList = None
stationInventory = {}
# use NOAA bulletin separator line to split up bulletins
bulletinSeparator = '####[0-9]{9}####'

args = None

def main():
    global args
    global countryList
    global stationList
    global stationInventory

    parser = argparse.ArgumentParser(description='Parses NOAA TAC SYNOP bulletins.')
    parser.add_argument('stationInventory',
                        metavar='station-inventory',
                        help='CSV file containing station metadata')
    parser.add_argument('input',
                        metavar='input-file',
                        help='the input file with SYNOP bulletins')
    parser.add_argument('-v', '--verbose', dest='verbose',
                        help='print verbose output of filtering etc.',
                        action='store_true')
    parser.add_argument('-f', '--filter', dest='filterfile',
                        metavar='filter-file',
                        help='YAML file specifying country and station filters',
                        required=False,
                        default=None)
    parser.add_argument('-d', '--date', dest='basedate',
                        metavar='base-date',
                        help='(yyyy-mm-dd) SYNOP does only encode day of month, so it is necessary to know which values belong to which month (and which year). Defaults to today.',
                        required=False,
                        default=datetime.date.today())
    args = parser.parse_args()

    if isinstance(args.basedate, str):
        try:
            args.basedate = datetime.datetime.strptime(args.basedate, '%Y-%m-%d')
        except ValueError:
            sys.exit('The specified base date seems to be invalid. Exiting.')

    if args.filterfile:
        filterSpec = None
        try:
            filterFile = open(args.filterfile, 'r')
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

    try:
        stationFile = open(args.stationInventory, 'r')
        stations = unicode(stationFile.read(), 'utf-8')
        stationFile.close()
        reader = csv.DictReader(StringIO.StringIO(stations.encode('utf-8')),
            quoting=csv.QUOTE_ALL, delimiter=',')
        for row in reader:
            stationInventory[row['wmo']] = { 'ele': row['ele'], 'lat': row['lat'] }
    except IOError:
        sys.exit('Could not read station inventory file, please check if it exists. Exiting.')

    data = ''
    try:
        inputFile = open(args.input, 'r')
        data = inputFile.read()
        inputFile.close()
        # convert newlines into spaces and remove carriage returns
        data = data.replace('\n', ' ')
        data = data.replace('\r', '')
        # collapse spaces
        data = ' '.join(data.split())
    except IOError:
        sys.exit('Could not read input file, please check if it exists. Exiting.')

    # specify regular expression of what separates bulletins in the text file
    bulletins = re.split(bulletinSeparator, data)

    count = 0
    for bulletin in bulletins:
        bulletin = bulletin.strip()
        # first one will be usually empty
        if len(bulletin) == 0:
            continue
        count += 1
        processBulletin(bulletin, count)

def processBulletin(bulletin, count):
    mixedBulletin = False
    modifierType = None
    modifierSequence = None
    windIndicator = None
    timestamp = None

    # examine bulletin header
    # it is of the form TTAAii CCCC YYGGgg (BBB)
    # TT = data type, AA = country or region, ii = sequence nr
    # CCCC = issuer, YYGGgg = day of month, hour UTC and minute UTC

    # BBB is either RRx, CCx or AAx, where x = A..Z and RR = additional info (new data), CC = correction, AA = amendment
    # additional info = new data normally contained in the initial bulletin but transmitted later
    # amendment = additional data to reports already contained in the initial bulletin
    # correction = correction of reports already contained in the initial bulletin

    # for SYNOP we are interested only in SI..., SM.... and SN....
    # see https://www.wmo.int/pages/prog/www/ois/Operational_Information/Publications/WMO_386/AHLsymbols/TableB1.html
    # countries are two letter character codes (non-ISO), can be filtered
    bulletinHead = re.match('^S[IMN](' + countryList + ')[0-9]{2}\s([A-Z]{4})', bulletin)
    if bulletinHead:
        print()
        print('bulletin ' + str(count) + ', country: ' + bulletinHead.group(1) + ', issuer: ' + bulletinHead.group(2))
        # consume first part of bulletin incl. CCCC and YYGGgg
        bulletin = bulletin[19:]
        # consume optional BBB modifier
        bulletinMod = re.match('^(AA|CC|RR)([A-Z])\s', bulletin)
        if bulletinMod:
            modifierType = bulletinMod.group(1)
            modifierSequence = bulletinMod.group(2)
            print('modifier: ' + modifierType + ', sequence: ' + modifierSequence)
            bulletin = bulletin[4:]

        # decide whether MMMM group (e.g. AAXX) occurs only once or more often
        # since we are only interested in AAXX here, we can safely assume that if XX occurs only once it is only present at the start of the bulletin
        if bulletin.count('XX') <= 1:
            if not bulletin.startswith('AAXX'):
                verbosePrint('discarding bulletin not containing data from fixed surface land stations.')
                return
            # consume MMMM and YYGGi group which is valid for the entire bulletin
            bulletin = bulletin[4:]
            try:
                windIndicator = int(bulletin[5:6])
            except ValueError:
                windIndicator = -1
            day = bulletin[1:3]
            hour = bulletin[3:5]

            year = args.basedate.year
            month = args.basedate.month
            if day > args.basedate.day:
                month -= 1
            timestamp = datetime.datetime(year, month, int(day), int(hour))
            print('timestamp: ' + str(timestamp))
            bulletin = bulletin[7:]
        else:
            mixedBulletin = True

        # we have now reached the level of individual stations
        stations = bulletin.split('=')
        for station in stations:
            station = station.strip()
            # discard empty report
            if len(station) == 0:
                continue
            if station.endswith('NIL'):
                verbosePrint('discarding NIL report.')
                continue

            if mixedBulletin:
                if not station.startswith('AAXX'):
                    verbosePrint('discarding station report not containing data from fixed surface land stations.')
                    continue
                else:
                    # consume MMMM and YYGGi group of station
                    station = station[4:]
                    windIndicator =  int(station[5:6])
                    day = station[1:3]
                    hour = station[3:5]

                    year = args.basedate.year
                    month = args.basedate.month
                    if day > args.basedate.day:
                        month -= 1
                    timestamp = datetime.datetime(year, month, int(day), int(hour))
                    print('day: ' + str(timestamp))
                    station = station[7:]
            # consume IIiii (station number)
            stationId = station[:5]
            if not stationList or int(stationId) in stationList:
                station = station[6:]
                print('decoding report from station ' + stationId + '.')
                processStation(stationId, timestamp, windIndicator, station)
            else:
                verbosePrint('discarding report from station ' + stationId + ', not in list.')
    else:
        verbosePrint('discarding non-SYNOP or geographically irrelevant bulletin.')

def processStation(stationId, timestamp, windIndicator, synop):
    verbosePrint(synop)

    data = {}
    # split SYNOP into its parts
    split = synop.split(' 333 ')
    land = split[0]
    if len(split) > 1:
        clim = split[1]
    else:
        clim = ''
    # discard regional section 5 if present
    if ' 555 ' in clim:
        clim = clim[:clim.find(' 555 ') - 1]

    # iihVV - precipitation and weather indicators, visibility
    precipitationIndicator = land[:1]
    weatherIndicator = land[1:2]
    # cloud base and visibility are omitted
    land = land[6:]

    # Nddff - cloud cover, wind direction and speed
    data['cloud_cover'] = land[:1]
    if data['cloud_cover'] == '/':
        data['cloud_cover'] = None
    try:
        data['wind_direction'] = int(land[1:3]) * 10
    except ValueError:
        data['wind_direction'] = None
    try:
        data['wind_speed'] = int(land[3:5])
    except ValueError:
        data['wind_speed'] = None
    # wind speed may be > 99, look for 00fff
    if data['wind_speed'] == 99 and land[6:8] == '00':
        data['wind_speed'] = int(land[8:11])
        land = land[12:]
    else:
        land = land[6:]
    # wind is specified in knots, have to convert to m/s
    if (windIndicator == 3 or windIndicator == 4) and data['wind_speed'] != None:
        data['wind_speed'] = round(data['wind_speed'] * 0.514444, 2)
    # if no wind indicator omit wind data to avoid inconsistencies
    if windIndicator == -1:
        data['wind_direction'] = None
        data['wind_speed'] = None

    # 1sTTT - temperature
    if land[0:1] == '1':
        try:
            # temperature is specified in 10ths of degrees
            data['temperature'] = float(land[2:5]) / 10
            # negative temperature
            if land[1:2] == '1':
                data['temperature'] = 0 - data['temperature']
            # no temperature sign, omit temperature altogether
            if land[1:2] == '/':
                data['temperature'] = None
        except ValueError:
            data['temperature'] = None
    else:
        data['temperature'] = None
    land = land[6:]

    # 2sTTT (or 29UUU) - dew point temperature or relative humidity
    if land[0:1] == '2':
        try:
            sign = int(land[1:2])
            value = float(land[2:5])
            if sign == 9:
                data['dew_point_temperature'] = None
                data['rel_humidity'] = value
            else:
                data['dew_point_temperature'] = value / 10
            if sign == 1:
                data['dew_point_temperature'] = 0 - data['dew_point_temperature']
            data['rel_humidity'] = round(relHumidity(data['temperature'], data['dew_point_temperature']), 1)
        except ValueError:
            data['dew_point_temperature'] = None
            data['rel_humidity'] = None
    land = land[6:]

    # 3PPPP - pressure at station level
    try:
        if land[4:5] == '/':
            data['station_pressure'] = int(land[1:4])
        else:
            data['station_pressure'] = float(land[1:5]) / 10

        # is there a better cutoff level?
        if data['station_pressure'] < 200:
            data['station_pressure'] += 1000
    except ValueError:
        data['station_pressure'] = None

    data['reduced_pressure'] = computeQFF(data['station_pressure'], data['temperature'], stationInventory[stationId]['ele'], stationInventory[stationId]['lat'])

    # 4PPPP group omitted because reduced pressure (QFF) is computed
    # why? different reduction methods are in use, but consistency is important
    land = land[6:]

    # 5appp - pressure tendency and amount of change omitted
    if land[0:1] == '5':
        land = land[6:]

    print(data)

# see https://www.wmo.int/pages/prog/www/IMOP/meetings/SI/ET-Stand-1/Doc-10_Pressure-red.pdf
# for a discussion of different reduction formulae
# formula used here is Formula 16 in the document which accounts for
# gravity variations due to latitude and lower temperatures
def computeQFF(pressure, temperature, elevation, latitude):
    if pressure == None or temperature == None or elevation == None or latitude == None:
        return None

    T = 1
    if temperature < -7:
        T = 0.5 * temperature + 275
    elif temperature >= -7 and temperature < 2:
        T = 0.535 * temperature + 275.6
    elif temperature >= 2:
        T = 1.07 * temperature + 274.5

    return round(pressure * math.exp(float(elevation) * 0.034163 * (1 - 0.0026373 * math.cos(2 * float(latitude))) / T), 2)

def relHumidity(temp, dewPointTemp):
    # approximation based on Magnus formula
    # from http://www.wetterochs.de/wetter/feuchte.html
    if temp >= 0:
        a = 7.5
        b = 237.3
    else:
        a = 7.6
        b = 240.7

    return math.pow(10, 2 + (a * dewPointTemp / (b + dewPointTemp)) - (a * temp / (b + temp)))

def verbosePrint(output):
    if args and args.verbose:
        print(output)

if __name__ == "__main__":
    main()
