import os
from pathlib import Path
from typing import Optional, Union

from flask import Flask, current_app
from flask_api import status
from sqlalchemy.exc import SQLAlchemyError

from buildingmotif.api.views.library import blueprint as library_blueprint
from buildingmotif.api.views.model import blueprint as model_blueprint
from buildingmotif.api.views.parser import blueprint as parsers_blueprint
from buildingmotif.api.views.template import blueprint as template_blueprint
from buildingmotif.building_motif.building_motif import BuildingMOTIF


def _after_request(response):
    """Commit or rollback the session.

    :param response: response
    :type response: Flask.response
    :return: response
    :rtype: Flask.response
    """
    try:
        current_app.building_motif.session.commit()
    except SQLAlchemyError:
        current_app.building_motif.session.rollback()

    current_app.building_motif.Session.remove()
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "*"

    return response


def _after_error(error):
    """Returns request with a 500 and the error message.

    :param error: python error
    :type error: Error
    :return: flask error response
    :rtype: Flask.response
    """
    return str(error), status.HTTP_500_INTERNAL_SERVER_ERROR


def create_app(
    DB_URI,
    shacl_engine: Optional[str] = "pyshacl",
    graph_store_path: Optional[Union[str, Path]] = None,
):
    """Creates a Flask API.

    :param db_uri: database URI
    :type db_uri: str
    :param shacl_engine: the name of the engine to use for validation: "pyshacl", "shifty", or "topquadrant". Using topquadrant
        requires Java to be installed on this machine, and the "topquadrant" feature on BuildingMOTIF,
        defaults to "pyshacl"
    :type shacl_engine: str, optional
    :param graph_store_path: directory for the Oxigraph graph store. Defaults
        to GRAPH_STORE_PATH or BuildingMOTIF's database-derived default.
    :return: flask app
    :rtype: Flask.app
    """
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        DB_URI=DB_URI,
        GRAPH_STORE_PATH=graph_store_path,
    )
    app.building_motif = BuildingMOTIF(
        app.config["DB_URI"],
        shacl_engine=shacl_engine,
        graph_store_path=app.config["GRAPH_STORE_PATH"],
    )

    app.after_request(_after_request)
    app.register_error_handler(Exception, _after_error)

    app.register_blueprint(library_blueprint, url_prefix="/libraries")
    app.register_blueprint(template_blueprint, url_prefix="/templates")
    app.register_blueprint(model_blueprint, url_prefix="/models")
    app.register_blueprint(parsers_blueprint, url_prefix="/parsers")

    return app


if __name__ == "__main__":
    """Run API."""
    db_uri = os.getenv("DB_URI")
    if db_uri is None:
        raise ValueError("Environment variable DB_URI not set.")

    app = create_app(db_uri, graph_store_path=os.getenv("GRAPH_STORE_PATH"))
    app.run(debug=True, host="0.0.0.0", threaded=False)
