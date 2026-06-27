# Command Line Interface

The `buildingmotif` command line tool will be available upon [installing BuildingMOTIF](/reference/developer_documentation). This provides several utilities for interacting with BuildingMOTIF:

- library loading
- running an API server
- BACnet Scanning

```{important}
Don't forget to set the `$DB_URI` variable (or supply the `-d`  option on the CLI tool) to make sure the CLI tool interacts with the right BuildingMOTIF database!
```

```{note}
BuildingMOTIF uses [Oxigraph](https://github.com/oxigraph/oxigraph) as its RDF graph store. By default, the store location is derived from the database URI (e.g. `mydb.sqlite` → `mydb.sqlite.oxigraph`). You can override this with the `$GRAPH_STORE_PATH` environment variable or the `--graph-store-path` CLI flag. Use a persistent path when running BuildingMOTIF as a long-lived service so that loaded ontology graphs survive restarts.
```

## Library Loading

Recall that a `Library` is a unit of distribution for shapes (for validation of metadata models) and templates (for generation of metadata models). Libraries can be loaded into BuildingMOTIF in 3 ways:

- **programmatically**, using the [`Library`](reference/apidoc/_autosummary/buildingmotif.dataclasses.library.html) class
- **individually**, using the `buildingmotif load` command (see below)
- **in bulk**, using the `buildingmotif load` command (see below)


### CLI Usage

```bash
usage: buildingmotif load [-h] [-d DB] [--dir DIR [DIR ...]] [-o ONT [ONT ...]] [-l LIBRARY_MANIFEST_FILE [LIBRARY_MANIFEST_FILE ...]] [--graph-store-path GRAPH_STORE_PATH]

Loads libraries from (1) local directories (--dir), (2) local or remote ontology files (--ont), or (3) library spec file (--libraries): the provided YML file into the BuildingMOTIF instance at $DB_URI

optional arguments:
  -h, --help            show this help message and exit
  -d DB, --db DB        Database URI of the BuildingMOTIF installation. Defaults to $DB_URI and then contents of "config.py"
  --dir DIR [DIR ...]   Path to a local directory containing the library
  -o ONT [ONT ...], --ont ONT [ONT ...]
                        Remote URL or local file path to an RDF ontology
  -l LIBRARY_MANIFEST_FILE [LIBRARY_MANIFEST_FILE ...], --libraries LIBRARY_MANIFEST_FILE [LIBRARY_MANIFEST_FILE ...]
                        Filename of the libraries YAML file specifying what should be loaded into BuildingMOTIF
  --graph-store-path GRAPH_STORE_PATH
                        Directory for the Oxigraph graph store. Defaults to $GRAPH_STORE_PATH or BuildingMOTIF's database-derived default.
```


### Bulk Library Loading

To load multiple libraries into BuildingMOTIF, create a `libraries.yml` file that describes the libraries to load and where they can be found.

Use the `buildingmotif load` command to load all libraries described in the `libraries.yml` file into BuildingMOTIF:

```bash
buildingmotif load -l libraries.yml
```

The YAML-encoded file contains a list of key-value "documents". Each document corresponds to a library to be loaded into BuildingMOTIF. There are three ways to specify a library: by directory, ontology URL, and `git` repository.

**Use `buildingmotif get_default_libraries_yml` to create an example `libraries.default.yml` file in the current directory.**

#### Directory

Using the `directory` key, point to a local directory containing template and shape files. The library will take on the name of the immediately enclosing directory. In the example below `libraries.yml` file, the name of the library will be "ZonePAC":

```yaml
# load a library from a local directory
- directory: libraries/ZonePAC/
```

#### Ontology

Using the `ontology` key, point to a local *or* remote URL containing an RDF graph containing shapes. Templates will be automatically inferred from the shape descriptions. The name of the library will be given by the name of the graph (pulled from a `<name> a owl:Ontology` triple in the graph).

```yaml
# load an ontology library from a remote URL
- ontology: https://github.com/BrickSchema/Brick/releases/download/nightly/Brick.ttl
```

#### Git Repository

Using the `git` key, point to a directory in a branch of a remote git repository. The repository will be temporarily cloned and the corresponding directory (in the given branch) will be loaded into BuildingMOTIF using the same mechanism as for the `directory` key. The `git` document requires the `repo` (URL), `branch` (string) and `path` (string) keys to be provided:

```yaml
# load a directory from a remote directory hosted in a github repo
- git:
    repo: https://github.com/NREL/BuildingMOTIF
    branch: main
    path: libraries/chiller-plant
```

### Loading Individual Libraries

You can load invidual diretories or ontologies into a BuildingMOTIF instance directly using the command line.

#### Directory

Use the `--dir` flag to pass the names of directories. The library will take on the name of the immediately enclosing directory. In the example below, the name of the library will be "directory":

```bash
buildingmotif load --dir path/to/library/directory
```

#### Ontology

Use the `--ont` key to specify a local *or* remote URL containing an RDF graph containing shapes. Templates will be automatically inferred from the shape descriptions. The name of the library will be given by the name of the graph (pulled from a `<name> a owl:Ontology` triple in the graph).

The example below loads the nightly version of the Brick ontology into BuildingMOTIF from a remote URL

```bash
buildingmotif load --ont https://github.com/BrickSchema/Brick/releases/download/nightly/Brick.ttl
```

The example below loads a local copy of the ASHRAE 223P ontology into BuildingMOTIF

```bash
buildingmotif load --ont 223p.ttl
```

### BACnet Scanning

```bash
usage: buildingmotif scan [-h] -o OUTPUT_FILE [-ip IP]

Scans a BACnet network and generates a JSON file for later processing

optional arguments:
  -h, --help            show this help message and exit
  -o OUTPUT_FILE, --output_file OUTPUT_FILE
                        Output file for BACnet scan
  -ip IP                ip address of BACnet network to scan
```

The BuildingMOTIF CLI includes a BACnet scanner, which can be accessed by invoking the `scan` subcommand. This command takes two inputs:
  - **Output file** - Where the scan information will be saved
  - **IP address** - The IP address to bind to and the subnet of the BACnet network. Example `172.24.0.2/32`

The output file generated by this command can be loaded into BuildingMOTIF by calling the `load()` function on the `BACnetNetwork` ingress.

## BuildingMOTIF API Server

To run a copy of the BuildingMOTIF API server, use `buildingmotif serve`:

```
usage: buildingmotif serve [-h] [-b BIND] [-p PORT] [-d DB] [--graph-store-path GRAPH_STORE_PATH]

Serves the BuildingMOTIF API on the indicated host:port

optional arguments:
  -h, --help            show this help message and exit
  -b BIND, --bind BIND  Address on which to bind the API server
  -p PORT, --port PORT  Listening port for the API server
  -d DB, --db DB        Database URI of the BuildingMOTIF installation. Defaults to $DB_URI and then contents of "config.py"
  --graph-store-path GRAPH_STORE_PATH
                        Directory for the Oxigraph graph store. Defaults to $GRAPH_STORE_PATH or BuildingMOTIF's database-derived default.
```
