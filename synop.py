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

    decodedData = []

    parser = argparse.ArgumentParser(description='Parses NOAA TAC SYNOP bulletins.')
    parser.add_argument('stationInventory',
                        metavar='station-inventory',
                        help='CSV file containing station metadata')
    parser.add_argument('input',
                        metavar='input-file',
                        help='the input file with SYNOP bulletins')
    parser.add_argument('output',
                        metavar='output-file',
                        help='the output file where to write decoded data')
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
            stationInventory[row['wmo']] = row
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
        decodedData = decodedData + processBulletin(bulletin, count)

    try:
        print('Writing to output file ' + args.output + '...')
        outputFile = open(args.output, 'w')
        writer = csv.DictWriter(outputFile, fieldnames=['station_id', 'timestamp', 'modifier_type', 'modifier_sequence',
            'temperature', 'dew_point_temperature', 'rel_humidity', 'wind_direction', 'wind_speed', 'gust_speed',
            'station_pressure', 'reduced_pressure', 'cloud_cover', 'sun_duration', 'precipitation_amount',
            'precipitation_duration', 'current_weather', 'snow_depth'],
            quoting=csv.QUOTE_ALL, delimiter=',')

        writer.writeheader()
        for dataRow in decodedData:
            if dataRow['modifier'] != None:
                dataRow['modifier_type'] = dataRow['modifier']['type']
                dataRow['modifier_sequence'] = dataRow['modifier']['sequence']
            else:
                dataRow['modifier_type'] = None
                dataRow['modifier_sequence'] = None
            del dataRow['modifier']

            if dataRow['precipitation'] != None:
                dataRow['precipitation_amount'] = dataRow['precipitation']['amount']
                dataRow['precipitation_duration'] = dataRow['precipitation']['duration']
            else:
                dataRow['precipitation_amount'] = None
                dataRow['precipitation_duration'] = None
            del dataRow['precipitation']

            writer.writerow(dataRow)
    except IOError:
        sys.exit('Could not open output file. Exiting.')

def processBulletin(bulletin, count):
    mixedBulletin = False
    modifierType = None
    modifierSequence = None
    windIndicator = None
    timestamp = None

    decodedData = []
    modifierType = None
    modifierSequence = None

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
                decodedData.append(processStation(stationId, timestamp, windIndicator, modifierType, modifierSequence, station))
            else:
                verbosePrint('discarding report from station ' + stationId + ', not in list.')
    else:
        verbosePrint('discarding non-SYNOP or geographically irrelevant bulletin.')

    return decodedData

def processStation(stationId, timestamp, windIndicator, modifierType, modifierSequence, synop):
    verbosePrint(synop)

    data = {}
    data['station_id'] = stationId
    data['timestamp'] = timestamp
    data['modifier'] = None

    if modifierType != None and modifierSequence != None:
        data['modifier'] = {'type': modifierType, 'sequence': modifierSequence}

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

    if stationId in stationInventory:
        data['reduced_pressure'] = computeQFF(data['station_pressure'], data['temperature'], stationInventory[stationId]['ele'], stationInventory[stationId]['lat'])
    else:
        data['reduced_pressure'] = None
    land = land[6:]

    # 4PPPP group omitted because reduced pressure (QFF) is computed
    # why? different reduction methods are in use, but consistency is important
    land = land[6:]

    # 5appp - pressure tendency and amount of change omitted
    if land[0:1] == '5':
        land = land[6:]

    # 6RRRt - precipitation amount and time frame
    # not published - no precipitation
    if precipitationIndicator == '3':
        data['precipitation'] = [{'amount': 0, 'time': None}]
    # not published - no measurement
    elif precipitationIndicator == '4':
        data['precipitation'] = None
    if land[0:1] == '6':
        data['precipitation'] = decodePrecipitation(land[0:5])
        land = land[6:]

    if land[0:1] == '7':
        try:
            data['current_weather'] = int(land[1:3])
        except ValueError:
            data['current_weather'] = None
        land = land[6:]
    else:
        data['current_weather'] = None

    # 8NCCC - cloud type information - omitted
    # 9GGgg - time of observation - omitted

    ### climatological part
    if len(clim) > 0:

        # discard everything before 4...
        while len(clim) > 0 and int(clim[0:1]) < 4:
            clim = clim[6:]

        # 4Esss - snow depth
        if clim[0:1] == '4':
            try:
                data['snow_depth'] = int(clim[2:5])
                if data['snow_depth'] == 997:
                    data['snow_depth'] = 0.5
                elif data['snow_depth'] == 998:
                    data['snow_depth'] = 0.01
                elif data['snow_depth'] == 999:
                    data['snow_depth'] = None
            except ValueError:
                data['snow_depth'] = None
            clim = clim[6:]
        else:
            data['snow_depth'] = None

        # 55SSS - daily hours of sunshine (of the previous day) in 10ths of hours - omitted
        # 553SS - duration of sunshine in the last hour in 10ths of hours
        while len(clim) > 0 and int(clim[0:1]) < 6 and clim[0:3] != '553':
            clim = clim[6:]

        if clim[0:3] == '553':
            try:
                data['sun_duration'] = int(clim[3:5]) / 10
            except ValueError:
                data['sun_duration'] = None
            clim = clim[6:]
        else:
            data['sun_duration'] = None

        while len(clim) > 0 and int(clim[0:1]) < 6:
            clim = clim[6:]
        # 6RRRt - amount and duration of precipitation (like in Section 1)
        if clim[0:1] == '6':
            precipitation = decodePrecipitation(clim[0:5])
            if 'precipitation' not in data.keys() or data['precipitation'] == None:
                data['precipitation'] = precipitation
            elif precipitation != None:
                data['precipitation'].append(precipitation)
        elif 'precipitation' not in data.keys():
            data['precipitation'] = None
        # 7RRRR - total amount of precipitation in the last 24 hours - omitted
        while int(clim[0:1]) < 9:
            clim = clim[6:]

        # 910ff - highest gust in the last 10 min
        while len(clim) > 0 and int(clim[0:1]) == 9 and not clim[0:3] == '910':
            clim = clim[6:]
        if clim[0:3] == '910':
            try:
                data['gust_speed'] = int(clim[3:5])
            except ValueError:
                data['gust_speed'] = None
            # gust speed may be > 99, look for 00fff
            if data['gust_speed'] == 99 and clim[6:8] == '00':
                data['gust_speed'] = int(clim[8:11])
                clim = clim[12:]
            else:
                clim = clim[6:]
            # speed is specified in knots, have to convert to m/s
            if (windIndicator == 3 or windIndicator == 4) and data['gust_speed'] != None:
                data['gust_speed'] = round(data['gust_speed'] * 0.514444, 2)
            # if no wind indicator omit wind data to avoid inconsistencies
            if windIndicator == -1:
                data['gust_speed'] = None
        else:
            data['gust_speed'] = None
        # 911ff - highest gust during the period covered by past weather - omitted
    else:
        data['snow_depth'] = None
        data['sun_duration'] = None
        data['gust_speed'] = None

    return data

def decodePrecipitation(precipGroup):
    precipitation = {}

    try:
        amount = float(precipGroup[1:4])
        if amount == 990:
            amount = 0.05
        elif amount > 990:
            amount = (amount - 990) / 10

        duration = int(precipGroup[4:5])
        if duration == 0:
            raise ValueError
        elif duration == 1:
            duration = 6
        elif duration == 2:
            duration = 12
        elif duration == 3:
            duration = 18
        elif duration == 4:
            duration = 24
        elif duration == 5:
            duration = 1
        elif duration == 6:
            duration = 2
        elif duration == 7:
            duration = 3
        elif duration == 8:
            duration = 9
        elif duration == 9:
            duration = 15

        precipitation = {'amount': amount, 'duration': duration}
    except ValueError:
        precipitation = None

    return precipitation

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
