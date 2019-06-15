# Stdlib Imports
import configparser
import signal
import os
import sys
import logging

# Non standard Library imports
from pid import PidFile
from daemon import DaemonContext

# Internal Package imports
from exceptions import ConfigError


class BaseDaemon(object):
    def __init__(self, config_file='daemon.ini'):
        self.config = configparser.ConfigParser()
        self.config.read(config_file)

        config_section = self.config_section or None
        required_configs = [config_section, 'LOGGING']
        for conf in required_configs:
            if conf not in self.config.sections():
                raise ConfigError(f'{conf} config missing.')

        self.daemon_config = self.config[config_section]
        self.log_config = self.config['LOGGING']

        # Gather Daemon ctx config options
        self.uid = self.daemon_config.getint('uid') or 0
        self.gid = self.daemon_config.getint('gid') or 0
        self.pid_file = self.daemon_config.get('pid_file')

        self.sig_map = {signal.SIGTERM: self.shutdown, signal.SIGTSTP: self.shutdown}

        # Create logger
        self.logger = logging.getLogger(__name__)

        self.log_file = self.log_config.get('logfile')
        if '~' in self.log_file:
            self.log_file = os.path.expanduser(self.log_file)

        # Configure logger
        self.log_handler = logging.FileHandler(self.log_file)
        log_formatter = logging.Formatter(self.log_config.get('format', raw=True))
        self.log_handler.setFormatter(log_formatter)
        self.logger.addHandler(self.log_handler)
        self.logger.setLevel(logging.DEBUG)

    def get_context(self):
        return DaemonContext(uid=self.uid, gid=self.gid, files_preserve=[self.log_handler.stream, ],
                             pidfile=PidFile(self.pid_file), stderr=self.log_handler.stream,
                             stdout=self.log_handler.stream, signal_map=self.sig_map)

    def check_pid(self):
        try:
            os.stat(self.pid_file)
            return True
        except IOError:
            return False

    def get_pid(self):
        with open(self.pid_file, 'r') as pid_file:
            pid = pid_file.read()
        return pid

    def shutdown(self, signum, frame):  # signum and frame are mandatory
        self.logger.info(f'System shut down Daemon with signum: {signum}')
        sys.exit(0)

