rm logindata.json -f
./carelink_carepartner_api_login.py
scp logindata.json raspi-zero:sensors/carelink/
