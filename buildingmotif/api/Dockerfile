FROM python:3.11

# Copy project
ADD buildingmotif /opt/buildingmotif
ADD libraries /opt/libraries
ADD migrations /opt/migrations
COPY alembic.ini /opt/
COPY pyproject.toml /opt/
COPY poetry.lock /opt/
ADD docs /opt/docs
ADD buildingmotif/api/start.sh /opt/start.sh
WORKDIR /opt/

# Install dpeendencies
RUN pip install poetry==1.4.0 && poetry config virtualenvs.create false
RUN ls /opt && poetry install
RUN chmod +x /opt/start.sh

CMD /opt/start.sh
