import time
import os
import argparse

from pythonping import ping as pping
from influxdb import InfluxDBClient

from base_daemon import BaseDaemon


class PingDaemon(BaseDaemon):

    def __init__(self, config_file='daemon.ini'):

        # Set this Daemon Class's config section before Inherited class instantiation
        self.config_section = "PING-DAEMON"

        # Instantiate the inherited BaseDaemon class
        BaseDaemon.__init__(self, config_file=config_file)

        self.my_config = self.config[self.config_section]

        # Get the Ping Daemons DB config
        self.db_config = self.config['PING-DB']

        self.targets = [target.strip() for target in self.my_config.get('targets').split(',')]

        self.daemon_ctx = self.get_context()

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

    def get_ping(self, host):

        try:
            ping_object = pping(host)
            min_ms = float(ping_object.rtt_min_ms)
            max_ms = float(ping_object.rtt_max_ms)
            avg_ms = float(ping_object.rtt_avg_ms)
        except OSError as e:
            self.logger.exception(f'Caught OS error during ping, Logging 0 ping time. Error was:  {e}')
            min_ms = 0.0
            max_ms = 0.0
            avg_ms = 0.0

        # Takes the python-ping object and forms the influxdb insert data then returns all three write points in a list.
        min_insert = {"measurement": "min_rtt", "tags": {"host": host},
                      "fields": {"min_rtt_ms": min_ms}}
        avg_insert = {"measurement": "avg_rtt", "tags": {"host": host},
                      "fields": {"avg_rtt_ms": max_ms}}
        max_insert = {"measurement": "max_rtt", "tags": {"host": host},
                      "fields": {"max_rtt_ms": avg_ms}}
        return [min_insert, avg_insert, max_insert]

    def main(self):
        interval = self.db_config.getint('write_interval')
        db_client = self.db_client()
        while True:
            for host in self.targets:
                ping_insert = self.get_ping(host)
                db_client.write_points(ping_insert)
                time.sleep(interval)

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
