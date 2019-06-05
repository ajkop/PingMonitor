import signal
import sys
import time
import os
import logging
import argparse
import configparser
from pid import PidFile

from pythonping import ping as pping
from daemon import DaemonContext
from influxdb import InfluxDBClient

from exceptions import ConfigError


class PingDaemon:
    def __init__(self, config_file='daemon.ini'):
        # Read ini file into config
        self.config = configparser.ConfigParser()
        self.config.read(config_file)

        # Iterate over required configs and raise exception if not found in provided config file.
        required_configs = ['DAEMON', 'DB', 'LOGGING']

        for conf in required_configs:
            if conf not in self.config.sections():
                raise ConfigError(f'{conf} config missing.')

        self.daemon_config = self.config['DAEMON']
        self.db_config = self.config['DB']
        log_config = self.config['LOGGING']

        # Create logger
        self.logger = logging.getLogger(__name__)

        self.log_file = log_config.get('logfile')
        if '~' in self.log_file:
            self.log_file = os.path.expanduser(self.log_file)

        # Configure logger
        log_handler = logging.FileHandler(self.log_file)
        log_formatter = logging.Formatter(log_config.get('format', raw=True))
        log_handler.setFormatter(log_formatter)
        self.logger.addHandler(log_handler)
        self.logger.setLevel(logging.DEBUG)

        # Gather Daemon ctx config options
        uid = self.daemon_config.getint('uid')
        gid = self.daemon_config.getint('gid')
        self.pid_file = self.daemon_config.get('pid_file')
        self.targets = [target.strip() for target in self.daemon_config.get('targets').split(',')]

        sig_map = {signal.SIGTERM: self.shutdown, signal.SIGTSTP: self.shutdown}

        # Create Daemon context
        self.daemon_ctx = DaemonContext(uid=uid, gid=gid, files_preserve=[log_handler.stream, ],
                                        pidfile=PidFile(self.pid_file), stderr=log_handler.stream,
                                        stdout=log_handler.stream, signal_map=sig_map)

        self.args = self.parser()

    @staticmethod
    def parser():
        parser = argparse.ArgumentParser(description='CLI to Manage the PingDaemon')
        parser.add_argument('--start', action="store_true", default=False, help='Start the Daemon')
        parser.add_argument('--stop', action="store_true", default=False, help='Stop the Daemon')
        parser.add_argument('--restart', action="store_true", default=False, help='Restart the Daemon')
        parser.add_argument('--status', action="store_true", default=False, help='Check the status of the Daemon, '
                                                                                 'will output if its running or not, '
                                                                                 'as well as PID and recent logs.')
        return parser.parse_args()

    def db_client(self):
        # Grab config
        db_name = self.db_config.get('name')
        db_host = self.db_config.get('host')
        db_user = self.db_config.get('username')
        db_pass = self.db_config.get('password')
        db_port = self.db_config.getint('port')
        use_ssl = self.db_config.getboolean('use_ssl')
        timeout = self.db_config.getint('timeout')

        # Create Client and switch to DB
        client = InfluxDBClient(host=db_host, port=db_port, username=db_user, password=db_pass, ssl=use_ssl,
                                database=db_name, timeout=timeout)
        return client

    def shutdown(self, signum, frame):  # signum and frame are mandatory
        self.logger.info(f'System shut down Daemon with signum: {signum}')
        sys.exit(0)

    def main(self):
        interval = self.db_config.getint('write_interval')
        db_client = self.db_client()
        while True:
            for host in self.targets:
                # Attempt to ping the host target, has its own try catch to ensure the daemon
                # continues even during outages.
                try:
                    r = pping(host)

                    min_insert = {"measurement": "min_rtt", "tags": {"host": f"{host}"},
                                  "fields": {"min_rtt_ms": float(r.rtt_min_ms)}}
                    avg_insert = {"measurement": "avg_rtt", "tags": {"host": f"{host}"},
                                  "fields": {"avg_rtt_ms": float(r.rtt_avg_ms)}}
                    max_insert = {"measurement": "max_rtt", "tags": {"host": f"{host}"},
                                  "fields": {"max_rtt_ms": float(r.rtt_max_ms)}}
                    db_client.write_points([min_insert, avg_insert, max_insert])
                    time.sleep(interval)
                except OSError as e:
                    self.logger.exception(f'Caught OS error during ping: {e}')

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

    def start(self):
        if self.check_pid():
            print('Daemon already started, cannot start.')
        else:
            self.logger.info(f'Starting PingDaemon on targets: {self.targets}')
            with self.daemon_ctx:
                self.main()

    def stop(self):
        if self.check_pid():
            self.logger.info('Closing Ping Daemon')
            with open(self.pid_file, 'r') as lock_file:
                pid = lock_file.read()
                os.kill(int(pid), 15)
        else:
            print('Daemon is not running')

    def restart(self):
        if self.check_pid():
            self.stop()

        self.start()
        self.status()

    def status(self):
        if self.check_pid():
            print(f'Daemon is running with PID: {self.get_pid()}')
            print('Last ten lines of logfile:')
            with open(self.log_file) as log_file:
                lines = log_file.readlines()
                for line in lines[-10:]:
                    print(line.strip())
        else:
            print('Daemon not running')


if __name__ == "__main__":
    pd = PingDaemon()
    args = pd.args
    if args.start:
        pd.start()
    elif args.stop:
        pd.stop()
    elif args.restart:
        pd.restart()
    elif args.status:
        pd.status()
    else:
        print('No argument provided. Check --help for available arguments')
