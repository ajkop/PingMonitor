class ConfigError(Exception):
    """ Error with provided config """


class SpeedTestError(Exception):
    """ Generic error with SpeedTest"""


class MissingSPSectionError(SpeedTestError):
    """ Missing Section in speed test XML"""


class NoServerFound(SpeedTestError):
    """ Unable to find server for speedtest """
