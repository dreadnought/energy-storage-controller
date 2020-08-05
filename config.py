import json
import os
import pytz

def load_config(file_name):
    f = open(file_name, 'r')
    config = json.load(f)
    f.close()
    return config

dirname = os.path.dirname(__file__)
config = load_config(os.path.join(dirname, 'config.json'))
tz = pytz.timezone(config["general"]["time_zone"])