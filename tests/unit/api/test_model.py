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
    Model.create(name="urn:my_model", description="the best model")
    Model.create(name="https://example.com")

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
    model = Model.create(name="urn:my_model")

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
    model = Model.create(name="urn:my_model")
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
    model = Model.create(name="urn:my_model")
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
    model = Model.create(name="urn:my_model")
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


def test_model_manifest(client, building_motif):
    # Set up
    model = Model.create(name="urn:my_model")
    library_1 = Library.load(ontology_graph="tests/unit/fixtures/shapes/shape1.ttl")
    model.update_manifest(library_1.get_shape_collection())

    results = client.get(
        f"/models/{model.id}/manifest", headers={"Accept": "text/turtle"}
    )
    print(results.data)
    manifest = Graph().parse(data=results.data, format="ttl")

    # Assert
    assert results.status_code == 200
    assert isomorphic(manifest, model.get_manifest().graph)


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
    model = Model.create(name="urn:my_model")
    assert isomorphic(model.graph, default_graph)

    # Action
    results = client.patch(f"/models/{model.id}/graph", data=graph_data)

    # Assert
    assert results.status_code == 400


def test_update_model_graph_bad_graph_value(client, building_motif):
    # Set up
    model = Model.create(name="urn:my_model")
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
    brick = Library.load(ontology_graph="tests/unit/fixtures/Brick.ttl")
    assert brick is not None
    library_1 = Library.load(ontology_graph="tests/unit/fixtures/shapes/shape1.ttl")
    assert library_1 is not None
    library_2 = Library.load(directory="tests/unit/fixtures/templates")
    assert library_2 is not None
    brick = Library.load(
        ontology_graph="tests/unit/fixtures/Brick.ttl", overwrite=False
    )
    assert brick is not None

    BLDG = Namespace("urn:building/")
    model = Model.create(name=BLDG)
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
    library = Library.load(ontology_graph="tests/unit/fixtures/shapes/shape1.ttl")
    assert library is not None

    # Action
    results = client.post(
        "/models/-1/validate",
        headers={"Content-Type": "application/json"},
        json={"library_ids": [library.id]},
    )

    # Assert
    assert results.status_code == 404


def test_validate_model_no_args(client, building_motif, shacl_engine):
    building_motif.shacl_engine = shacl_engine
    # Set up
    BLDG = Namespace("urn:building/")
    model = Model.create(name=BLDG)

    # Action
    results = client.post(
        f"/models/{model.id}/validate",
        headers={"Content-Type": "application/json"},
    )

    # Assert
    assert results.status_code == 200, results.data
    assert results.get_json().keys() == {"message", "reasons", "valid"}
    assert isinstance(results.get_json()["message"], str)
    assert results.get_json()["valid"]
    assert results.get_json()["reasons"] == {}


def test_validate_model_no_library_ids(client, building_motif, shacl_engine):
    building_motif.shacl_engine = shacl_engine
    # Set up
    BLDG = Namespace("urn:building/")
    model = Model.create(name=BLDG)

    # Action
    results = client.post(
        f"/models/{model.id}/validate",
        headers={"Content-Type": "application/json"},
        json={},
    )

    # Assert
    assert results.status_code == 200, results.data
    assert results.get_json().keys() == {"message", "reasons", "valid"}
    assert isinstance(results.get_json()["message"], str)
    assert results.get_json()["valid"]
    assert results.get_json()["reasons"] == {}


def test_validate_model_bad_library_ids(client, building_motif):
    # Set up
    BLDG = Namespace("urn:building/")
    model = Model.create(name=BLDG)

    # Action
    results = client.post(
        f"/models/{model.id}/validate",
        headers={"Content-Type": "application/json"},
        json={"library_ids": [-1, -2, -3]},
    )

    # Assert
    assert results.status_code == 400, results.data


def test_validate_model_bad_args(client, building_motif):
    # Set up
    library = Library.load(ontology_graph="tests/unit/fixtures/shapes/shape1.ttl")
    assert library is not None
    BLDG = Namespace("urn:building/")
    model = Model.create(name=BLDG)

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
    assert results.status_code == 400, results.data

    # Action 2
    results = client.post(
        f"/models/{model.id}/validate",
        headers={"Content-Type": "application/json"},
        json=[],
    )

    # Assert 2
    assert results.status_code == 400, results.data


def test_validate_model_against_shapes(client, building_motif, shacl_engine):
    building_motif.shacl_engine = shacl_engine
    # Load libraries
    brick = Library.load(ontology_graph=str(PROJECT_DIR / "libraries/brick/Brick.ttl"))
    unit = Library.load(
        ontology_graph=str(PROJECT_DIR / "libraries/qudt/VOCAB_QUDT-UNITS-ALL.ttl")
    )
    qk = Library.load(
        ontology_graph=str(
            PROJECT_DIR / "libraries/qudt/VOCAB_QUDT-QUANTITY-KINDS-ALL.ttl"
        )
    )
    ashrae_g36 = Library.load(
        directory=str(PROJECT_DIR / "libraries/ashrae/guideline36/")
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
            "shape_collection_ids": [
                ashrae_g36.get_shape_collection().id,
                brick.get_shape_collection().id,
                unit.get_shape_collection().id,
                qk.get_shape_collection().id,
            ],
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


def test_get_model_node_subgraph_endpoint_basic_and_self_contained(
    client, building_motif
):
    # Setup
    model = Model.create(name="urn:my_model_node_subgraph_api")
    s = URIRef("urn:ex:s")
    p = URIRef("urn:ex:p")
    o1 = URIRef("urn:ex:o1")
    o2 = URIRef("urn:ex:o2")

    # s -> o1; and o1 -> o2
    model.add_triples((s, p, o1))
    model.add_triples((o1, p, o2))

    # Persist if needed
    building_motif.session.commit()

    # Act: self_contained=false should only include triples where subject == s
    res = client.get(
        f"/models/{model.id}/node_subgraph",
        query_string={"node": str(s), "self_contained": "false"},
    )
    assert res.status_code == 200, res.data
    g = Graph().parse(data=res.data, format="turtle")
    assert (s, p, o1) in g
    assert (o1, p, o2) not in g

    # Act: self_contained=true should include follow-on triples starting at o1
    res2 = client.get(
        f"/models/{model.id}/node_subgraph",
        query_string={"node": str(s), "self_contained": "true"},
    )
    assert res2.status_code == 200, res2.data
    g2 = Graph().parse(data=res2.data, format="turtle")
    assert (s, p, o1) in g2
    assert (o1, p, o2) in g2


def test_get_model_node_subgraph_endpoint_missing_node_returns_400(
    client, building_motif
):
    model = Model.create(name="urn:my_model_node_subgraph_api2")
    res = client.get(f"/models/{model.id}/node_subgraph")
    assert res.status_code == 400


def test_validate_endpoint_include_templates_returns_inlined_templates_with_parameters_and_types(
    client, building_motif, shacl_engine
):
    # Ensure SHACL engine configured
    building_motif.shacl_engine = shacl_engine

    # Load libraries used for validation (shapes and Brick ontology)
    brick = Library.load(ontology_graph="tests/unit/fixtures/Brick.ttl")
    library_1 = Library.load(ontology_graph="tests/unit/fixtures/shapes/shape1.ttl")
    library_2 = Library.load(directory="tests/unit/fixtures/templates")

    # Build a simple model with a VAV missing required sensors
    BLDG = Namespace("urn:building/")
    model = Model.create(name=BLDG)
    model.add_triples((BLDG["vav1"], A, BRICK.VAV))

    # Call the validate endpoint with include_templates=true to get generated templates
    res = client.post(
        f"/models/{model.id}/validate?include_templates=true",
        headers={"Content-Type": "application/json"},
        json={"library_ids": [library_1.id, library_2.id, brick.id]},
    )
    assert res.status_code == 200, res.data

    data = res.get_json()
    assert "templates" in data
    assert isinstance(data["templates"], list)
    assert len(data["templates"]) >= 1
    assert all(
        isinstance(t.get("template_id"), int) and t["template_id"] > 0
        for t in data["templates"]
    )
    # Verify focus is included for each template and includes the VAV focus node
    for t in data["templates"]:
        assert "focus" in t
        # focus should be a string URI or null
        assert (t["focus"] is None) or isinstance(t["focus"], str)
    assert any(t["focus"] == str(BLDG["vav1"]) for t in data["templates"])

    # Verify each template payload includes in-lined TTL body and parameter types,
    # and that the TTL body contains the rdf:type triples for the declared parameters.
    all_types = set()
    for t in data["templates"]:
        assert "body" in t and "parameters" in t and "template_id" in t
        assert isinstance(t["template_id"], int) and t["template_id"] > 0
        ttl_body = t["body"]
        params = t["parameters"]
        # Body should parse as TTL
        g = Graph().parse(data=ttl_body, format="ttl")

        # For each parameter, ensure the reported rdf:type values are actually present in the body
        for p in params:
            pname = p["name"]
            pnode = URIRef(f"urn:___param___#{pname}")
            types_in_graph = {str(o) for o in g.objects(pnode, RDF.type)}
            assert len(p["types"]) >= 1
            assert set(p["types"]).issubset(types_in_graph)
            all_types.update(p["types"])

    # Expect at least the two missing sensor classes from shape1 constraints
    assert "https://brickschema.org/schema/Brick#Temperature_Sensor" in all_types
    assert "https://brickschema.org/schema/Brick#Air_Flow_Sensor" in all_types


def test_validate_endpoint_include_templates_via_json_body(
    client, building_motif, shacl_engine
):
    # Ensure SHACL engine configured
    building_motif.shacl_engine = shacl_engine

    # Load libraries used for validation (shapes and Brick ontology)
    brick = Library.load(ontology_graph="tests/unit/fixtures/Brick.ttl")
    library_1 = Library.load(ontology_graph="tests/unit/fixtures/shapes/shape1.ttl")
    library_2 = Library.load(directory="tests/unit/fixtures/templates")

    # Build a simple model with a VAV missing required sensors
    BLDG = Namespace("urn:building/")
    model = Model.create(name=BLDG)
    model.add_triples((BLDG["vav1"], A, BRICK.VAV))

    # Call the validate endpoint with include_templates=True in the JSON body
    res = client.post(
        f"/models/{model.id}/validate",
        headers={"Content-Type": "application/json"},
        json={
            "library_ids": [library_1.id, library_2.id, brick.id],
            "include_templates": True,
        },
    )
    assert res.status_code == 200, res.data

    data = res.get_json()
    assert "templates" in data
    assert isinstance(data["templates"], list)
    assert len(data["templates"]) >= 1
    assert all(
        isinstance(t.get("template_id"), int) and t["template_id"] > 0
        for t in data["templates"]
    )
    for t in data["templates"]:
        assert "template_id" in t
        assert isinstance(t["template_id"], int) and t["template_id"] > 0
    # Verify at least one template is focused on the VAV we created
    assert any(t.get("focus") == str(BLDG["vav1"]) for t in data["templates"])
