FROM python:3.10-alpine

RUN apk update && apk upgrade

WORKDIR /SigmaBot/

COPY ./assets /SigmaBot/assets
COPY ./languages /SigmaBot/languages

COPY ./*.py /SigmaBot/

COPY ./requirements.txt /SigmaBot/requirements.txt

RUN pip install -r requirements.txt 

CMD python index.py