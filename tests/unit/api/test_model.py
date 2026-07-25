from pathlib import Path

from rdflib import Graph, Namespace, URIRef
from rdflib.compare import isomorphic, to_isomorphic
from rdflib.namespace import RDF

from buildingmotif.dataclasses import Library, Model
from buildingmotif.namespaces import BRICK, A

graph_data = """
    @prefix owl: <http://www.w3.org/2002/07/owl#> .
    @prefix sh: <http://www.w3.org/ns/shacl#> .
    @prefix : <urn:my_model#> .
    @prefix bmotif: <https://nrel.gov/BuildingMOTIF#> .

    :shape1 a bmotif:HVAC ;
    .

    :shape2 a bmotif:Lighting ;
    .

    :shape3 a bmotif:Electrical ;
    .
"""

default_graph = Graph()
default_graph.add(
    (URIRef("urn:my_model"), RDF.type, URIRef("http://www.w3.org/2002/07/owl#Ontology"))
)

PROJECT_DIR = Path(__file__).resolve().parents[3]


def test_get_all_models(client, building_motif):
    # Setup
    Model.create(uri="urn:my_model", description="the best model")
    Model.create(uri="https://example.com")

    # Act
    results = client.get("/models")

    # Assert
    assert results.status_code == 200

    db_models = building_motif.table_connection.get_all_db_models()
    assert results.json == [
        {
            "id": m.id,
            "name": m.name,
            "description": m.description,
            "graph_id": m.graph_id,
        }
        for m in db_models
    ]


def test_get_model(client, building_motif):
    # Setup
    model = Model.create(uri="urn:my_model")

    # Act
    results = client.get(f"/models/{model.id}")

    # Assert
    assert results.status_code == 200

    db_model = building_motif.table_connection.get_db_model(model.id)
    assert results.json == {
        "id": db_model.id,
        "name": db_model.name,
        "graph_id": db_model.graph_id,
        "description": db_model.description,
    }


def test_get_model_not_found(client):
    # Act
    results = client.get("/models/-1")

    # Assert
    assert results.status_code == 404
    assert results.json == {"message": "ID: -1"}


def test_get_model_graph(client, building_motif):
    # Setup
    model = Model.create(uri="urn:my_model")
    model.add_graph(Graph().parse(data=graph_data, format="ttl"))
    excepted_graph = to_isomorphic(model.graph)
    building_motif.session.commit()

    # Act
    results = client.get(f"/models/{model.id}/graph")

    # Assert
    assert results.status_code == 200
    results_graph = Graph().parse(data=results.data, format="ttl")
    assert isomorphic(results_graph, excepted_graph)


def test_get_model_graph_not_found(client):
    # Act
    results = client.get("/models/-1/graph")

    # Assert
    assert results.status_code == 404
    assert results.json == {"message": "ID: -1"}


def test_update_model_graph_overwrite(client, building_motif):
    # Set up
    model = Model.create(uri="urn:my_model")
    assert isomorphic(model.graph, default_graph)

    # Action
    results = client.put(
        f"/models/{model.id}/graph",
        data=graph_data,
        headers={"Content-Type": "application/xml"},
    )
    model = Model.load(model.id)

    # Assert
    assert results.status_code == 200
    results_graph = Graph().parse(data=results.data, format="ttl")
    expected_graph = Graph().parse(data=graph_data, format="ttl")
    assert isomorphic(results_graph, expected_graph)
    assert isomorphic(model.graph, expected_graph)


def test_update_model_graph_append(client, building_motif):
    # Set up
    model = Model.create(uri="urn:my_model")
    assert isomorphic(model.graph, default_graph)

    # Action
    results = client.patch(
        f"/models/{model.id}/graph",
        data=graph_data,
        headers={"Content-Type": "application/xml"},
    )
    model = Model.load(model.id)

    # Assert
    assert results.status_code == 200
    results_graph = Graph().parse(data=results.data, format="ttl")
    expected_graph = Graph().parse(data=graph_data, format="ttl")
    print(results_graph.serialize(format="ttl"))
    print("++++")
    print((expected_graph + default_graph).serialize(format="ttl"))
    assert isomorphic(results_graph, expected_graph + default_graph)
    assert isomorphic(model.graph, expected_graph + default_graph)


def test_update_model_graph_not_found(client, building_motif):
    # Act
    results = client.patch(
        "/models/-1/graph", data=graph_data, headers={"Content-Type": "application/xml"}
    )

    # Assert
    assert results.status_code == 404
    assert results.json == {"message": "ID: -1"}


def test_update_model_graph_no_header(client, building_motif):
    # Set up
    model = Model.create(uri="urn:my_model")
    assert isomorphic(model.graph, default_graph)

    # Action
    results = client.patch(f"/models/{model.id}/graph", data=graph_data)

    # Assert
    assert results.status_code == 400


def test_update_model_graph_bad_graph_value(client, building_motif):
    # Set up
    model = Model.create(uri="urn:my_model")
    assert isomorphic(model.graph, default_graph)

    # Action
    results = client.patch(
        f"/models/{model.id}/graph",
        data="not xml",
        headers={"Content-Type": "application/xml"},
    )

    # Assert
    assert results.status_code == 400


def test_create_model(client, building_motif):
    results = client.post(
        "/models",
        json={"name": "https://example.com"},
    )

    assert results.status_code == 201

    assert isinstance(results.json["id"], int)
    assert isinstance(results.json["graph_id"], str)

    assert results.json["name"] == "https://example.com"
    assert results.json["description"] == ""

    assert isinstance(Model.load(results.json["id"]), Model)


def test_create_model_with_description(client, building_motif):
    results = client.post(
        "/models",
        json={"name": "https://example.com", "description": "it's so cool"},
    )

    assert results.status_code == 201

    assert isinstance(results.json["id"], int)
    assert isinstance(results.json["graph_id"], str)

    assert results.json["name"] == "https://example.com"
    assert results.json["description"] == "it's so cool"

    assert isinstance(Model.load(results.json["id"]), Model)


def test_create_model_no_json(client, building_motif):
    results = client.post(
        "/models",
    )

    assert results.status_code == 400


def test_create_model_no_name(client, building_motif):
    results = client.post(
        "/models",
        json={},
    )

    assert results.status_code == 400


def test_create_model_bad_name(client, building_motif):
    results = client.post(
        "/models",
        json={"name": "I have spaces."},
    )

    assert results.status_code == 400

    assert len(building_motif.table_connection.get_all_db_models()) == 0


def test_validate_model(client, building_motif, shacl_engine):
    building_motif.shacl_engine = shacl_engine
    # Set up
    brick = Library.from_ontology("tests/unit/fixtures/Brick.ttl")
    assert brick is not None
    library_1 = Library.from_ontology("tests/unit/fixtures/shapes/shape1.ttl")
    assert library_1 is not None
    library_2 = Library.from_directory("tests/unit/fixtures/templates")
    assert library_2 is not None
    brick = Library.from_ontology("tests/unit/fixtures/Brick.ttl", overwrite=False)
    assert brick is not None

    BLDG = Namespace("urn:building/")
    model = Model.create(uri=BLDG)
    model.add_triples((BLDG["vav1"], A, BRICK.VAV))

    # Action
    results = client.post(
        f"/models/{model.id}/validate",
        headers={"Content-Type": "application/json"},
        json={"library_ids": [library_1.id, library_2.id, brick.id]},
    )

    # Assert
    assert results.status_code == 200, results.data

    assert results.get_json().keys() == {"message", "reasons", "valid"}
    assert isinstance(results.get_json()["message"], str)
    response = results.get_json()
    assert "urn:building/vav1" in response["reasons"], "vav1 should be in the response"
    if shacl_engine == "pyshifty":
        # the pyshifty engine returns an AlgebraicValidationContext whose reasons
        # are derived from the algebra (witness atoms) rather than the legacy
        # GraphDiff messages, so assert on structure rather than exact strings
        vav1_reasons = response["reasons"]["urn:building/vav1"]
        assert len(vav1_reasons) >= 1
        assert all(isinstance(r, str) and r for r in vav1_reasons)
    else:
        assert set(response["reasons"]["urn:building/vav1"]) == {
            "urn:building/vav1 expected at least 1 instance(s) of brick:Temperature_Sensor on path brick:hasPoint",
            "urn:building/vav1 expected at least 1 instance(s) of brick:Air_Flow_Sensor on path brick:hasPoint",
        }
    assert not results.get_json()["valid"]

    # Set up
    model.add_triples((BLDG["vav1"], A, BRICK.VAV))
    model.add_triples((BLDG["vav1"], BRICK.hasPoint, BLDG["temp_sensor"]))
    model.add_triples((BLDG["temp_sensor"], A, BRICK.Temperature_Sensor))
    model.add_triples((BLDG["vav1"], BRICK.hasPoint, BLDG["flow_sensor"]))
    model.add_triples((BLDG["flow_sensor"], A, BRICK.Air_Flow_Sensor))

    # Action
    results = client.post(
        f"/models/{model.id}/validate",
        headers={"Content-Type": "application/json"},
        json={"library_ids": [library_1.id, library_2.id, brick.id]},
    )

    # Assert
    assert results.status_code == 200, results.data

    assert results.get_json().keys() == {"message", "reasons", "valid"}
    assert isinstance(results.get_json()["message"], str)
    assert results.get_json()["valid"]
    assert results.get_json()["reasons"] == {}


def test_validate_model_bad_model_id(client, building_motif, shacl_engine):
    building_motif.shacl_engine = shacl_engine
    # Set up
    library = Library.from_ontology("tests/unit/fixtures/shapes/shape1.ttl")
    assert library is not None

    # Action
    results = client.post(
        "/models/-1/validate",
        headers={"Content-Type": "application/json"},
        json={"library_ids": [library.id]},
    )

    # Assert
    assert results.status_code == 404


def test_validate_model_bad_shacl_engine(client):
    BLDG = Namespace("urn:building/")
    model = Model.create(uri=BLDG)

    results = client.post(
        f"/models/{model.id}/validate?shacl_engine=bad-engine",
        headers={"Content-Type": "application/json"},
        json={},
    )

    assert results.status_code == 400
    assert "Unsupported SHACL engine 'bad-engine'" in results.get_json()["message"]


def test_validate_model_no_args(client, building_motif, shacl_engine):
    building_motif.shacl_engine = shacl_engine
    # Set up
    BLDG = Namespace("urn:building/")
    model = Model.create(uri=BLDG)

    # Action
    results = client.post(
        f"/models/{model.id}/validate",
        headers={"Content-Type": "application/json"},
    )

    # Assert
    assert results.status_code == 200
    assert results.get_json().keys() == {"message", "reasons", "valid"}
    assert isinstance(results.get_json()["message"], str)
    assert results.get_json()["valid"]
    assert results.get_json()["reasons"] == {}


def test_validate_model_no_library_ids(client, building_motif, shacl_engine):
    building_motif.shacl_engine = shacl_engine
    # Set up
    BLDG = Namespace("urn:building/")
    model = Model.create(uri=BLDG)

    # Action
    results = client.post(
        f"/models/{model.id}/validate",
        headers={"Content-Type": "application/json"},
        json={},
    )

    # Assert
    assert results.status_code == 200
    assert results.get_json().keys() == {"message", "reasons", "valid"}
    assert isinstance(results.get_json()["message"], str)
    assert results.get_json()["valid"]
    assert results.get_json()["reasons"] == {}


def test_validate_model_bad_library_ids(client, building_motif):
    # Set up
    BLDG = Namespace("urn:building/")
    model = Model.create(uri=BLDG)

    # Action
    results = client.post(
        f"/models/{model.id}/validate",
        headers={"Content-Type": "application/json"},
        json={"library_ids": [-1, -2, -3]},
    )

    # Assert
    assert results.status_code == 400


def test_validate_model_bad_args(client, building_motif):
    # Set up
    library = Library.from_ontology("tests/unit/fixtures/shapes/shape1.ttl")
    assert library is not None
    BLDG = Namespace("urn:building/")
    model = Model.create(uri=BLDG)

    # Action 1
    results = client.post(
        f"/models/{model.id}/validate",
        headers={"Content-Type": "application/json"},
        json=[
            {
                "library_id": library.id,
                # no shape_uri
            }
        ],
    )

    # Assert 1
    assert results.status_code == 400

    # Action 2
    results = client.post(
        f"/models/{model.id}/validate",
        headers={"Content-Type": "application/json"},
        json=[],
    )

    # Assert 2
    assert results.status_code == 400


def test_validate_model_against_shapes(client, building_motif, shacl_engine):
    building_motif.shacl_engine = shacl_engine
    # Load libraries
    Library.from_ontology(str(PROJECT_DIR / "libraries/brick/Brick.ttl"))
    ashrae_g36 = Library.from_directory(
        str(PROJECT_DIR / "libraries/ashrae/guideline36/")
    )

    # build model
    BLDG = Namespace("http://example.org/building/")
    medium_office_model = Model.create(BLDG)
    medium_office_model.graph.parse(
        PROJECT_DIR
        / "notebooks/mediumOffice-validation/mediumOffice_brick_compiled.ttl",
        format="ttl",
    )
    manifest = Graph().parse(
        PROJECT_DIR
        / "notebooks/mediumOffice-validation/constraints/mediumOffice_constraints.ttl"
    )
    medium_office_model.get_manifest().add_graph(manifest)

    # action
    results = client.post(
        f"/models/{medium_office_model.id}/validate_shape",
        headers={"Content-Type": "application/json"},
        json={
            "shape_collection_ids": [ashrae_g36.get_shape_collection().id],
            "shape_uris": [
                "urn:ashrae/g36/5.16.14/multiple-zone-vav-ahu-afdd/fc-3",
                "urn:ashrae/g36/5.16.14/multiple-zone-vav-ahu-afdd/fc-4",
            ],
            "target_class": str(BRICK["AHU"]),
        },
    )

    # assert
    assert (
        len(results.json["urn:ashrae/g36/5.16.14/multiple-zone-vav-ahu-afdd/fc-3"]) == 0
    ), results.data
    assert (
        len(results.json["urn:ashrae/g36/5.16.14/multiple-zone-vav-ahu-afdd/fc-4"]) == 3
    ), results.data
