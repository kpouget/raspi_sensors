#! /usr/bin/env python3

import json

import carelink_client2

client = carelink_client2.CareLinkClient(tokenFile="logindata.json")
if not client.init():
    print("Couldn't initialize ...")
    exit(1)

client.printUserInfo()
data = client.getRecentData()

print("Saving data.json ...")
with open("data.json", "w") as f:
    json.dump(data, f, indent=4)
