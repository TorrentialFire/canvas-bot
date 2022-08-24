FROM python:3.8-alpine3.16
COPY . /cbot
RUN pip install -r /cbot/requirements.txt
CMD python /cbot/cbot.py /cbot/canvas-bot-config.json