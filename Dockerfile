FROM python:3.10-alpine

RUN apk update && apk upgrade

WORKDIR /SigmaBot/

COPY ./assets /SigmaBot/assets
COPY ./languages /SigmaBot/languages

COPY ./client.py /SigmaBot/client.py
COPY ./database.py /SigmaBot/database.py
COPY ./handlers.py /SigmaBot/handlers.py
COPY ./index.py /SigmaBot/index.py
COPY ./language.py /SigmaBot/language.py
COPY ./views.py /SigmaBot/views.py

COPY ./requirements.txt /SigmaBot/requirements.txt

RUN pip install -r requirements.txt 

CMD python index.py