import argparse
import logging
import shutil
import sys
from os import getenv
from pathlib import Path

from buildingmotif import BuildingMOTIF
from buildingmotif.bin.library import add_commands
from buildingmotif.dataclasses import Library
from buildingmotif.ingresses.bacnet import BACnetNetwork

cli = argparse.ArgumentParser(
    prog="buildingmotif", description="CLI Interface for common BuildingMOTIF tasks"
)
subparsers = cli.add_subparsers(dest="subcommand")

subcommands = {}
log = logging.getLogger()
log.setLevel(logging.INFO)

ONTOLOGY_FILE_SUFFIXES = ["ttl", "n3", "ntriples", "xml"]


# borrowing some ideas from https://gist.github.com/mivade/384c2c41c3a29c637cb6c603d4197f9f
def arg(*argnames, **kwargs):
    """Helper for defining arguments on subcommands"""
    return argnames, kwargs


def subcommand(*subparser_args, parent=subparsers):
    """Decorates a function and makes it available as a subcommand"""

    def decorator(func):
        parser = parent.add_parser(func.__name__, description=func.__doc__)
        for args, kwargs in subparser_args:
            parser.add_argument(*args, **kwargs)
        parser.set_defaults(func=func)
        subcommands[func] = parser

    return decorator


def subparser(*subparser_args, parent=subparsers):
    """Decorates a function and makes it available as a subparser"""

    def decorator(func):
        subcommand(*subparser_args, parent=parent)(func)

        subparser = subcommands[func].add_subparsers(dest=f"{func.__name__}_subcommand")

        def subcommand_decorator(*subparser_args, parent=subparser):
            return subcommand(*subparser_args, parent=parent)

        return subcommand_decorator

    return decorator


def get_db_uri(args) -> str:
    """
    Fetches the db uri from args, or prints the usage
    for the corresponding subcommand
    """
    db_uri = args.db
    if db_uri is not None:
        return db_uri
    db_uri = getenv("DB_URI")
    if db_uri is not None:
        return db_uri
    print("No DB URI could be found")
    subcommands[args.func].print_help()
    sys.exit(1)


@subcommand(
    arg(
        "-d",
        "--db",
        help="Database URI of the BuildingMOTIF installation. "
        'Defaults to $DB_URI and then contents of "config.py"',
    ),
    arg(
        "--dir",
        help="Path to a local directory containing the library",
        nargs="+",
    ),
    arg(
        "-o",
        "--ont",
        help="Remote URL or local file path to an RDF ontology",
        nargs="+",
    ),
    arg(
        "-l",
        "--libraries",
        help="Filename of the libraries YAML file specifying what "
        "should be loaded into BuildingMOTIF",
        nargs="+",
        dest="library_manifest_file",
    ),
)
def load(args):
    """
    Loads libraries from (1) local directories (--dir),
    (2) local or remote ontology files (--ont)
    (3) library spec file (--libraries): the provided YML file into the
      BuildingMOTIF instance at $DB_URI.
      Use 'get_default_libraries_yml' for the format of the expected libraries.yml file
    """
    db_uri = get_db_uri(args)
    bm = BuildingMOTIF(db_uri)
    bm.setup_tables()
    for directory in args.dir or []:
        Library.load(directory=directory)
    for ont in args.ont or []:
        Library.load(ontology_graph=ont)
    for library_manifest_file in args.library_manifest_file or []:
        manifest_path = Path(library_manifest_file)
        log.info(f"Loading buildingmotif libraries listed in {manifest_path}")
        Library.load_from_libraries_yml(str(manifest_path))
    bm.session.commit()


@subcommand()
def get_default_libraries_yml(_args):
    """
    Creates a default 'libraries.default.yml' file in the current directory
    that can be edited and used with buildingmotif
    """
    default_file = (
        Path(__file__).resolve().parents[1] / "resources" / "libraries.default.yml"
    )
    shutil.copyfile(default_file, "libraries.default.yml")
    print("libraries.default.yml created in the current directory")


@subcommand(
    arg(
        "-b",
        "--bind",
        help="Address on which to bind the API server",
        default="localhost",
    ),
    arg(
        "-p", "--port", help="Listening port for the API server", type=int, default=5000
    ),
    arg(
        "-d",
        "--db",
        help="Database URI of the BuildingMOTIF installation. "
        'Defaults to $DB_URI and then contents of "config.py"',
    ),
)
def serve(args):
    """
    Serves the BuildingMOTIF API on the indicated host:port
    """
    from buildingmotif.api.app import create_app

    db_uri = get_db_uri(args)
    webapp = create_app(db_uri)
    webapp.run(host=args.host, port=args.port, threaded=False)


def app():
    args = cli.parse_args()
    if args.subcommand is None:
        cli.print_help()
    else:
        args.func(args)


@subcommand(
    arg("-o", "--output_file", help="Output file for BACnet scan", required=True),
    arg("-ip", help="ip address of BACnet network to scan", default=None),
)
def scan(args):
    """Scans a BACnet network and generates a JSON file for later processing"""
    bacnet_network = BACnetNetwork(args.ip)
    bacnet_network.dump(Path(args.output_file))


@subparser()
def library(args):
    """A collection of commands for working with libraries"""


add_commands(library)

# entrypoint is actually defined in pyproject.toml; this is here for convenience/testing
if __name__ == "__main__":
    app()
