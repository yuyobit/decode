#!/usr/bin/env python

from __future__ import print_function
import argparse
from bulletin import processBulletin
import csv
import datetime
import glob
from output import writeCsvOutput
from output import writeSqliteOutput
import re
import settings
import StringIO
import sys
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

if __name__ == "__main__":
    main()
