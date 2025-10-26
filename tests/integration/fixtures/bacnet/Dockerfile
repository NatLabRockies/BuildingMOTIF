FROM python:3.12 as base

WORKDIR /opt

COPY requirements.txt .
RUN python3 -m pip install -r requirements.txt

COPY virtual_bacnet.py virtual_bacnet.py
COPY BACpypes.ini .
