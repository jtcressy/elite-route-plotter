FROM python:3-alpine

WORKDIR /app

ADD mqtt_version.py /app/mqtt_version.py

RUN pip3 install -r requirements.txt

CMD python3 mqtt_version.py
