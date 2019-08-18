from influxdb import InfluxDBClient

import datetime
import traceback


class Metrics:
    def __init__(self, database_name):
        self.client = InfluxDBClient('localhost', database=database_name, port=8086)
        self.database_name = database_name
        db_found = False
        for db in self.client.get_list_database():
            if db['name'] == database_name:
                db_found = True

        if not db_found:
            print('creating database')
            self.client.create_database(database_name)

        self.client.switch_database(database_name)

    def write_metric(self, points):
        for point in points:
            point['time'] = datetime.datetime.fromtimestamp(point['time']).isoformat()
        try:
            self.client.write_points(points, database=self.database_name)
        except Exception as e:
            print('faied to write metrics')
            print(e)
            print(traceback.format_exc())


if __name__ == '__main__':
    from config import config

    m = Metrics(database_name=config['influxdb']['database_name'])
