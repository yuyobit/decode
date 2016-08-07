#!/usr/bin/env python

from __future__ import print_function
import argparse
import datetime
import re
import sys
import yaml

stationList = []
countryList = None
# use NOAA bulletin separator line to split up bulletins
bulletinSeparator = '####[0-9]{9}####'

args = None

def main():
    global args
    global countryList
    global stationList

    parser = argparse.ArgumentParser(description='Parses NOAA TAC SYNOP bulletins.')
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
            windIndicator = int(bulletin[5:6])
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
                print(station)
            else:
                verbosePrint('discarding report from station ' + stationId + ', not in list.')
    else:
        verbosePrint('discarding non-SYNOP or geographically irrelevant bulletin.')

def verbosePrint(output):
    if args and args.verbose:
        print(output)

if __name__ == "__main__":
    main()
