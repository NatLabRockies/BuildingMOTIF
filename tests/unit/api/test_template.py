from flask_api import status
from rdflib import Graph, Namespace

from buildingmotif.dataclasses import Library, Model
from buildingmotif.namespaces import BRICK, A

BLDG = Namespace("urn:building/")

BINDINGS = b"""name,cav
zone1,cav1
zone2,cav2
"""


def test_get_all_templates(client, building_motif):
    # Setup
    lib = Library.create("my_library")
    lib.create_template("my_template")
    lib.create_template("your_template")

    # Act
    results = client.get("/templates")

    # Assert
    assert results.status_code == 200

    db_templates = building_motif.table_connection.get_all_db_templates()
    assert results.json == [
        {
            "id": t.id,
            "name": t.name,
            "body_id": t.body_id,
            "optional_args": t.optional_args,
            "library_id": t.library_id,
            "dependency_ids": [d.id for d in t.dependencies],
        }
        for t in db_templates
    ]


def test_get_template(client, building_motif):
    # Setup
    lib = Library.create("my_library")
    template = lib.create_template("my_template")

    # Act
    results = client.get(f"/templates/{template.id}")

    # Assert
    assert results.status_code == 200

    db_template = building_motif.table_connection.get_db_template(template.id)
    assert results.json == {
        "id": db_template.id,
        "name": db_template.name,
        "body_id": db_template.body_id,
        "optional_args": db_template.optional_args,
        "library_id": db_template.library_id,
        "dependency_ids": [d.id for d in db_template.dependencies],
    }


def test_get_template_with_parameters(client, building_motif):
    # Setup
    lib = Library.from_directory("tests/unit/fixtures/templates")
    zone = lib.get_template_by_name("zone")

    # Act
    results = client.get(f"/templates/{zone.id}?parameters=True")

    # Assert
    assert results.status_code == 200
    assert results.json["parameters"] == ["cav", "name"]


def test_get_template_not_found(client):
    # Act
    results = client.get("/templates/-1")

    # Assert
    assert results.status_code == 404
    assert results.json == {"message": "ID: -1"}


def test_evaluate_bindings(client, building_motif):
    model = Model.create(uri="urn:my_model")
    lib = Library.from_directory("tests/unit/fixtures/templates")
    zone = lib.get_template_by_name("zone")
    zone.inline_dependencies()
    assert zone.parameters == {"name", "cav"}

    results = client.post(
        f"/templates/{zone.id}/evaluate/bindings",
        json={
            "model_id": model.id,
            "bindings": {"name": {"@id": BLDG["zone1"]}, "cav": {"@id": BLDG["cav1"]}},
        },
    )

    assert results.status_code == status.HTTP_200_OK
    graph = Graph().parse(data=results.data, format="ttl")
    assert (model.name + "/" + BLDG["cav1"], A, BRICK.CAV) in graph
    assert (model.name + "/" + BLDG["zone1"], A, BRICK.HVAC_Zone) in graph
    assert (
        model.name + "/" + BLDG["zone1"],
        BRICK.isFedBy,
        model.name + "/" + BLDG["cav1"],
    ) in graph
    assert len(list(graph.triples((None, None, None)))) == 3


def test_evaluate_bindings_bad_templated_id(client, building_motif):
    model = Model.create(uri="urn:my_model")

    results = client.post(
        "/templates/-1/evaluate/bindings",
        json={
            "model_id": model.id,
            "bindings": {"name": {"@id": BLDG["zone1"]}, "cav": {"@id": BLDG["cav1"]}},
        },
    )

    assert results.status_code == 404


def test_evaluate_bindings_no_body(client, building_motif):
    lib = Library.from_directory("tests/unit/fixtures/templates")
    zone = lib.get_template_by_name("zone")
    zone.inline_dependencies()
    assert zone.parameters == {"name", "cav"}

    results = client.post(f"/templates/{zone.id}/evaluate/bindings")

    assert results.status_code == 400


def test_evaluate_bindings_bad_body(client, building_motif):
    model = Model.create(uri="urn:my_model")
    lib = Library.from_directory("tests/unit/fixtures/templates")
    zone = lib.get_template_by_name("zone")
    zone.inline_dependencies()
    assert zone.parameters == {"name", "cav"}

    results = client.post(
        f"/templates/{zone.id}/evaluate/bindings",
        json={
            # no model
            "bindings": {"name": {"@id": BLDG["zone1"]}, "cav": {"@id": BLDG["cav1"]}},
        },
    )

    assert results.status_code == 400

    results = client.post(
        f"/templates/{zone.id}/evaluate/bindings",
        json={
            "model_id": model.id,
            # no bindings
        },
    )

    assert results.status_code == 400


def test_evaluate_bindings_bad_model_id(client, building_motif):
    lib = Library.from_directory("tests/unit/fixtures/templates")
    zone = lib.get_template_by_name("zone")
    zone.inline_dependencies()
    assert zone.parameters == {"name", "cav"}

    results = client.post(
        f"/templates/{zone.id}/evaluate/bindings",
        json={
            "model_id": -1,
            "bindings": {"name": {"@id": BLDG["zone1"]}, "cav": {"@id": BLDG["cav1"]}},
        },
    )

    assert results.status_code == 404, results.data


def test_evaluate_ingress(client, building_motif):
    # create a 'MODEL' namespace here to scope the entities we create
    MODEL = Namespace("urn:my_model/")
    model = Model.create(uri=MODEL)
    lib = Library.from_directory("tests/unit/fixtures/templates")
    zone = lib.get_template_by_name("zone")
    zone.inline_dependencies()
    assert zone.parameters == {"name", "cav"}

    results = client.post(
        f"/templates/{zone.id}/evaluate/ingress?model_id={model.id}",
        data=BINDINGS,
    )

    assert results.status_code == status.HTTP_200_OK, results.data
    graph = Graph().parse(data=results.data, format="ttl")
    assert (MODEL["cav1"], A, BRICK.CAV) in graph
    assert (MODEL["zone1"], A, BRICK.HVAC_Zone) in graph
    assert (MODEL["zone1"], BRICK.isFedBy, MODEL["cav1"]) in graph
    assert (MODEL["cav2"], A, BRICK.CAV) in graph
    assert (MODEL["zone2"], A, BRICK.HVAC_Zone) in graph
    assert (MODEL["zone2"], BRICK.isFedBy, MODEL["cav2"]) in graph


def test_evaluate_ingress_no_body(client, building_motif):
    lib = Library.from_directory("tests/unit/fixtures/templates")
    zone = lib.get_template_by_name("zone")
    zone.inline_dependencies()
    assert zone.parameters == {"name", "cav"}

    results = client.post(f"/templates/{zone.id}/evaluate/ingress")

    assert results.status_code == 400


def test_evaluate_ingress_bad_body(client, building_motif):
    model = Model.create(uri="urn:my_model")
    lib = Library.from_directory("tests/unit/fixtures/templates")
    zone = lib.get_template_by_name("zone")
    zone.inline_dependencies()
    assert zone.parameters == {"name", "cav"}

    results = client.post(
        f"/templates/{zone.id}/evaluate/ingress",
        json={
            # no model
            "bindings": {"name": {"@id": BLDG["zone1"]}, "cav": {"@id": BLDG["cav1"]}},
        },
    )

    assert results.status_code == 400

    results = client.post(
        f"/templates/{zone.id}/evaluate/ingress",
        json={
            "model_id": model.id,
            # no bindings
        },
    )

    assert results.status_code == 400


def test_evaluate_ingress_bad_model_id(client, building_motif):
    lib = Library.from_directory("tests/unit/fixtures/templates")
    zone = lib.get_template_by_name("zone")
    zone.inline_dependencies()
    assert zone.parameters == {"name", "cav"}

    results = client.post(
        f"/templates/{zone.id}/evaluate/ingress?model_id=-1",
        json={
            "bindings": {"name": {"@id": BLDG["zone1"]}, "cav": {"@id": BLDG["cav1"]}},
        },
    )

    assert results.status_code == 404, results.data
