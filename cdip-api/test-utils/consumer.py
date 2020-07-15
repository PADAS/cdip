import time
import walrus
import json

db = walrus.Database(host='localhost', port=32769, db=0)

s1 = db.Stream('radios')

# The key 'radios' must exist for the ConsumerGroup create to work.
cgroup1 = db.consumer_group('cgroup-1', 'radios')
cgroup1.create()

# Block until new items are added to the stream.
# cgroup1.set_id('$')

last_id = 0

cnt = 0
while True:

    cnt = cnt + 1
    if cnt % 10 == 0:
        print('.', end='')

    try:
        item = cgroup1.read(count=1, block=1000)
        if item: print(item)
    except Exception as e:
        print(e)

    if item:
        last_id = item[0][0]
