from __future__ import print_function
import datetime
from lib import verbosePrint
import re
import settings
from synop import processSynop

def processBulletin(bulletin, count, basedate):
    modifierType = None
    modifierSequence = None
    windIndicator = None
    timestamp = None

    bulletinId = None
    bulletinIssuer = None
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

    # SYNOP: SI..., SM.... and SN....
    # METAR: SA...
    # see https://www.wmo.int/pages/prog/www/ois/Operational_Information/Publications/WMO_386/AHLsymbols/TableB1.html
    # countries are two letter character codes (non-ISO), can be filtered
    bulletinHead = re.match('((^S[A-Z])(' + settings.countryList + ')[0-9]{2})\s([A-Z]{4})', bulletin)
    if bulletinHead:
        print()
        bulletinId = bulletinHead.group(1)
        bulletinType = bulletinHead.group(2)
        bulletinIssuer = bulletinHead.group(4)
        print('bulletin ' + str(count) + ', country: ' + bulletinHead.group(3) + ', issuer: ' + bulletinIssuer)
        # consume first part of bulletin incl. CCCC and YYGGgg
        bulletin = bulletin[19:]
        # consume optional BBB modifier
        bulletinMod = re.match('^(AA|CC|RR)([A-Z])\s', bulletin)
        if bulletinMod:
            modifierType = bulletinMod.group(1)
            modifierSequence = bulletinMod.group(2)
            print('modifier: ' + modifierType + ', sequence: ' + modifierSequence)
            bulletin = bulletin[4:]

        if bulletinType == 'SI' or bulletinType == 'SM' or bulletinType == 'SN':
            synopBulletin(bulletin, basedate, bulletinId, bulletinIssuer, modifierType, modifierSequence)
    else:
        verbosePrint('discarding non-SYNOP/METAR/TEMP or geographically irrelevant bulletin.')

def synopBulletin(bulletin, basedate, bulletinId, bulletinIssuer, modifierType, modifierSequence):
    mixedBulletin = False

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

        year = basedate.year
        month = basedate.month
        if day > basedate.day:
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

                year = basedate.year
                month = basedate.month
                if day > basedate.day:
                    month -= 1
                timestamp = datetime.datetime(year, month, int(day), int(hour))
                print('day: ' + str(timestamp))
                station = station[7:]
        # consume IIiii (station number)
        stationId = station[:5]
        if not settings.stationList or int(stationId) in settings.stationList:
            station = station[6:]
            processSynop(stationId, timestamp, windIndicator, bulletinId, bulletinIssuer, modifierType, modifierSequence, station)
        else:
            verbosePrint('discarding report from station ' + stationId + ', not in list.')
