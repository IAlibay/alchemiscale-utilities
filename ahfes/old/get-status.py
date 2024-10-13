import os
from alchemiscale import AlchemiscaleClient, Scope, ScopedKey

user_id = os.environ['ALCHEMISCALE_ID']
user_key = os.environ['ALCHEMISCALE_KEY']
asc =  AlchemiscaleClient('https://api.alchemiscale.org', user_id, user_key)

with open('scoped-key.dat', 'r') as f:
    network_sk = f.read()

asc.get_network_status(network_sk)
