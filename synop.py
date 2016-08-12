from __future__ import print_function
from lib import computeQFF
from lib import relHumidity
from lib import verbosePrint
import settings

def processSynop(stationId, timestamp, windIndicator, bulletinId, bulletinIssuer, modifierType, modifierSequence, synop):
    # skip station if duplicate
    duplicates = filter(lambda data: data['station_id'] == stationId and data['timestamp'] == timestamp, settings.decodedData)
    for duplicate in duplicates:
        if duplicate['modifier'] == None and modifierType == None and modifierSequence == None:
            verbosePrint('Skipping duplicate report from station ' + stationId + '.')
            return
        elif duplicate['modifier'] != None and duplicate['modifier']['type'] == modifierType and duplicate['modifier']['sequence'] == modifierSequence:
            verbosePrint('Skipping duplicate report from station ' + stationId + '.')
            return

    print('decoding report from station ' + stationId + '.')
    verbosePrint(synop)

    data = {}
    data['station_id'] = stationId
    data['timestamp'] = timestamp
    data['bulletin_id'] = bulletinId
    data['bulletin_issuer'] = bulletinIssuer
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
        land = land[6:]
    else:
        data['temperature'] = None

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
    else:
        data['dew_point_temperature'] = None
        data['rel_humidity'] = None

    # 3PPPP - pressure at station level
    if land[0:1] == '3':
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

        if stationId in settings.stationInventory:
            data['pressure'] = computeQFF(data['station_pressure'], data['temperature'],
                settings.stationInventory[stationId]['ele'], settings.stationInventory[stationId]['lat'])
        else:
            data['pressure'] = None
        land = land[6:]
    else:
        data['station_pressure'] = None
        data['pressure'] = None

    # 4PPPP group omitted because reduced pressure (QFF) is computed
    # why? different reduction methods are in use, but consistency is important
    if land[0:1] == '4':
        land = land[6:]

    # 5appp - pressure tendency and amount of change omitted
    if land[0:1] == '5':
        land = land[6:]

    # 6RRRt - precipitation amount and time frame
    # not published - no precipitation
    if precipitationIndicator == '3':
        data['precipitation'] = [{'amount': 0, 'duration': None}]
    # not published - no measurement
    elif precipitationIndicator == '4':
        data['precipitation'] = None
    if land[0:1] == '6':
        data['precipitation'] = [decodePrecipitation(land[0:5])]
        land = land[6:]
    else:
        data['precipitation'] = None

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
                data['sun_duration'] = float(clim[3:5]) / 10
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
                data['precipitation'] = [precipitation]
            elif precipitation != None:
                data['precipitation'].append(precipitation)
        elif 'precipitation' not in data.keys():
            data['precipitation'] = None
        # 7RRRR - total amount of precipitation in the last 24 hours - omitted
        while len(clim) > 0 and int(clim[0:1]) < 9:
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

    settings.decodedData.append(data)

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
