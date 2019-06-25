def get_speed_data(self):
    # Creates the pyspeedtest object and gets the up/down data and forms it into influxdb write points
    st = self.speedtest()

    # 1 Byte is equal to 0.00000095367432 MB, Below we multiply the return byte/second metric to MB.
    down = st.download() * 0.00000095367432
    up = st.upload() * 0.00000095367432

    # Get the host server seperated from the port.
    host_server = st.host.split(':')[0]

    # Format the influxdb insert dict for each metric.
    up_insert = {"measurement": 'upload_speed', "tags": {'server': host_server}, "fields": {"MBps": up}}
    down_insert = {"measurement": 'download_speed', "tags": {'server': host_server}, "fields": {"MBps": down}}
    return [up_insert, down_insert]