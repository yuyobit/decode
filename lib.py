import math
import settings

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

def verbosePrint(output):
    if settings.verbose:
        print(output)
