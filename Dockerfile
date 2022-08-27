FROM python:3.8-alpine3.16

# Set the timezone
RUN apk add tzdata & \
    cd /usr/share/zoneinfo & \
    cp /usr/share/zoneinfo/America/Chicago /etc/localtime

COPY . /cbot
RUN pip install -r /cbot/requirements.txt
CMD python /cbot/cbot.py /cbot/canvas-bot-config.json