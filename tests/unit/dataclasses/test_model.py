import pytest
from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.compare import isomorphic
from rdflib.exceptions import ParserError
from rdflib.namespace import FOAF, XSD

from buildingmotif import BuildingMOTIF
from buildingmotif.dataclasses import (
    AlgebraicValidationContext,
    Library,
    Model,
    RepairWitness,
    ValidationContext,
)
from buildingmotif.namespaces import BRICK, OWL, RDF, RDFS, SH, A

BLDG = Namespace("urn:building/")


def test_create_model(clean_building_motif):
    model = Model.create(uri="https://example.com", description="a very good model")

    assert isinstance(model, Model)
    assert model.name == "https://example.com"
    assert model.description == "a very good model"
    assert isinstance(model.graph, Graph)


def test_create_model_bad_name(clean_building_motif):
    with pytest.raises(ValueError):
        Model.create(uri="I have spaces")

    assert len(clean_building_motif.table_connection.get_all_db_models()) == 0


def test_load_model(clean_building_motif):
    m = Model.create(uri="https://example.com", description="a very good model")
    m.graph.add((URIRef("http://example.org/alex"), RDF.type, FOAF.Person))

    result = Model.load(m.id)
    assert result.id == m.id
    assert result.name == m.name
    assert result.description == m.description
    assert isomorphic(result.graph, m.graph)

    # test model_load_by_name
    result = Model.load(name="https://example.com")
    assert result.id == m.id
    assert result.name == m.name
    assert result.description == m.description
    assert isomorphic(result.graph, m.graph)


def test_from_file_no_ontology_declaration(clean_building_motif):
    # this should fail because the file does not declare an ontology
    with pytest.raises(ValueError):
        Model.from_file("tests/unit/fixtures/smallOffice_brick.ttl")


def test_from_file(clean_building_motif):
    # Create a model from a file
    model = Model.from_file("tests/unit/fixtures/from_file_test.ttl")

    assert isinstance(model, Model)
    assert model.name == "https://example.com"
    assert model.description == "This is an example graph"
    assert len(model.graph) == 2


def test_from_file_weird_extensions(clean_building_motif):
    # Create a model from a file. the from_file_test.xyz is a turtle-formatted file
    # so even though the extension is .xyz, it should still be able to parse it
    # because rdflib defaults to turtle if it can't determine the format from the extension
    model = Model.from_file("tests/unit/fixtures/from_file_test.xyz")

    assert isinstance(model, Model)
    assert model.name == "https://example.com"
    assert model.description == "This is an example graph"
    assert len(model.graph) == 2

    # guesses 'turtle' because xmlbadext is not a valid extension
    with pytest.raises(ParserError):
        model = Model.from_file("tests/unit/fixtures/from_file_test.xmlbadext")


def test_from_graph(clean_building_motif):
    # Create a graph
    g = Graph()
    g.add((URIRef("https://example.com"), RDF.type, OWL.Ontology))
    g.add((URIRef("https://example.com"), RDFS.comment, Literal("Example description")))

    # Create a model from the graph
    model = Model.from_graph(g)

    assert isinstance(model, Model)
    assert model.name == "https://example.com"
    assert model.description == "Example description"
    assert len(model.graph) == 2


def test_update_model_manifest(clean_building_motif):
    m = Model.create(uri="https://example.com", description="a very good model")
    lib = Library.from_ontology("tests/unit/fixtures/shapes/shape1.ttl")
    assert lib is not None
    # update manifest with library
    m.add_to_manifest(lib.get_shape_collection())
    assert len(list(m.get_manifest().graph.subjects(RDF.type, SH.NodeShape))) == 2


def test_validate_model_manifest(clean_building_motif, shacl_engine):
    clean_building_motif.shacl_engine = shacl_engine
    m = Model.create(uri="https://example.com", description="a very good model")
    m.graph.add((URIRef("https://example.com/vav1"), A, BRICK.VAV))

    Library.from_ontology("tests/unit/fixtures/Brick.ttl")
    lib = Library.from_ontology("tests/unit/fixtures/shapes/shape1.ttl")
    assert lib is not None

    m.add_to_manifest(lib.get_shape_collection())

    # validate against manifest -- should fail
    result = m.validate()
    assert not result.valid

    # add triples to graph to validate
    m.graph.add(
        (
            URIRef("https://example.com/vav1"),
            BRICK.hasPoint,
            URIRef("https://example.com/flow"),
        )
    )
    m.graph.add((URIRef("https://example.com/flow"), A, BRICK.Air_Flow_Sensor))
    m.graph.add(
        (
            URIRef("https://example.com/vav1"),
            BRICK.hasPoint,
            URIRef("https://example.com/temp"),
        )
    )
    m.graph.add((URIRef("https://example.com/temp"), A, BRICK.Temperature_Sensor))

    # validate against manifest -- should pass
    result = m.validate()
    assert result.valid


def test_validate_model_manifest_with_imports(clean_building_motif, shacl_engine):
    clean_building_motif.shacl_engine = shacl_engine
    m = Model.create(uri="https://example.com", description="a very good model")
    m.graph.add((URIRef("https://example.com/vav1"), A, BRICK.VAV))

    # import brick
    Library.from_ontology("tests/unit/fixtures/Brick.ttl")

    # shape2.ttl attaches an import statement to the manifest
    lib = Library.from_ontology("tests/unit/fixtures/shapes/shape2.ttl")
    assert lib is not None

    m.add_to_manifest(lib.get_shape_collection())

    # add triples to graph to validate
    # using subclasses here -- buildingmotif must resolve the library import in order for these to validate correctly
    m.graph.add(
        (
            URIRef("https://example.com/vav1"),
            BRICK.hasPoint,
            URIRef("https://example.com/flow"),
        )
    )
    m.graph.add((URIRef("https://example.com/flow"), A, BRICK.Supply_Air_Flow_Sensor))
    m.graph.add(
        (
            URIRef("https://example.com/vav1"),
            BRICK.hasPoint,
            URIRef("https://example.com/temp"),
        )
    )
    m.graph.add(
        (URIRef("https://example.com/temp"), A, BRICK.Supply_Air_Temperature_Sensor)
    )

    # validate against manifest -- should pass now
    result = m.validate()
    assert result.valid, result.report_string


def test_validate_model_explicit_shapes(clean_building_motif, shacl_engine):
    clean_building_motif.shacl_engine = shacl_engine
    # load library
    Library.from_ontology("tests/unit/fixtures/Brick.ttl")
    lib = Library.from_ontology("tests/unit/fixtures/shapes/shape1.ttl")
    assert lib is not None

    BLDG = Namespace("urn:building/")
    m = Model.create(uri=BLDG)
    m.add_triples((BLDG["vav1"], A, BRICK.VAV))

    ctx = m.validate([lib.get_shape_collection()])
    assert not ctx.valid

    m.add_triples((BLDG["vav1"], A, BRICK.VAV))
    m.add_triples((BLDG["vav1"], BRICK.hasPoint, BLDG["temp_sensor"]))
    m.add_triples((BLDG["temp_sensor"], A, BRICK.Temperature_Sensor))
    m.add_triples((BLDG["vav1"], BRICK.hasPoint, BLDG["flow_sensor"]))
    m.add_triples((BLDG["flow_sensor"], A, BRICK.Air_Flow_Sensor))

    ctx = m.validate([lib.get_shape_collection()])
    assert ctx.valid

    assert len(ctx.diffset) == 0


def test_validate_model_with_failure(bm: BuildingMOTIF, shacl_engine):
    """
    Test that a model correctly validates
    """
    bm.shacl_engine = shacl_engine
    shape_graph_data = """
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix brick: <https://brickschema.org/schema/Brick#> .
@prefix : <urn:shape_graph/> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
: a owl:Ontology .
:zone_shape a sh:NodeShape ;
    sh:targetClass brick:HVAC_Zone ;
    sh:message "all HVAC zones must have a label" ;
    sh:property [
        sh:path rdfs:label ;
        sh:minCount 1 ;
    ] .
    """
    shape_graph = Graph().parse(data=shape_graph_data)
    shape_lib = Library.from_ontology(shape_graph)

    lib = Library.from_directory("tests/unit/fixtures/templates")
    zone = lib.get_template_by_name("zone")
    assert zone.parameters == {"name", "cav"}

    # create model from template
    model = Model.create(BLDG)
    bindings, hvac_zone_instance = zone.fill(BLDG)
    model.add_graph(hvac_zone_instance)

    # validate the graph (should fail because there are no labels)
    ctx = model.validate([shape_lib.get_shape_collection()])
    assert isinstance(ctx, (ValidationContext, AlgebraicValidationContext))
    assert not ctx.valid
    assert len(ctx.diffset) == 1
    diffs = [d for diff_set in ctx.diffset.values() for d in diff_set]
    assert len(diffs) == 1
    diff = diffs[0]
    if isinstance(ctx, AlgebraicValidationContext):
        assert isinstance(diff, RepairWitness)
        # pyshifty exposes the native algebraic cardinality constraint, not a
        # reconstructed W3C SHACL source-component name.
        assert diff.failed_component is None
        assert diff.constraint is not None
    else:
        assert diff.failed_component == SH.MinCountConstraintComponent

    model.add_triples((bindings["name"], RDFS.label, Literal("hvac zone 1")))
    # validate the graph (should now be valid)
    ctx = model.validate([shape_lib.get_shape_collection()])
    assert isinstance(ctx, (ValidationContext, AlgebraicValidationContext))
    assert ctx.valid


def test_model_compile(bm: BuildingMOTIF, shacl_engine):
    """Test that model compilation gives expected results"""
    bm.shacl_engine = shacl_engine
    small_office_model = Model.create("http://example.org/building/")
    small_office_model.graph.parse(
        "tests/unit/fixtures/smallOffice_brick.ttl", format="ttl"
    )

    brick = Library.from_ontology(
        "libraries/brick/Brick-full.ttl", infer_templates=False
    )

    compiled_model = small_office_model.compile([brick.get_shape_collection()])

    precompiled_model = Graph().parse(
        "tests/unit/fixtures/smallOffice_brick_compiled.ttl", format="ttl"
    )
    for s, p, o in list(precompiled_model):
        if isinstance(o, Literal) and o.datatype is None and o.language is None:
            precompiled_model.remove((s, p, o))
            precompiled_model.add((s, p, Literal(str(o), datatype=XSD.string)))

    in_first = precompiled_model - compiled_model.graph

    # passes if everything from precompiled_model is in compiled_model
    assert len(in_first) == 0


def test_get_manifest(clean_building_motif):
    BLDG = Namespace("urn:building/")
    model = Model.create(uri=BLDG)
    manifest = model.get_manifest()
    manifest.graph.add((URIRef("http://example.org/alex"), RDF.type, FOAF.Person))

    assert model.get_manifest() == manifest
    assert isomorphic(manifest.load(manifest.id).graph, manifest.graph)


def test_validate_with_manifest(clean_building_motif, shacl_engine):
    clean_building_motif.shacl_engine = shacl_engine
    g = Graph()
    g.parse(
        data="""
    @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
    @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
    @prefix skos: <http://www.w3.org/2004/02/skos/core#> .
    @prefix brick: <https://brickschema.org/schema/Brick#> .
    @prefix sh: <http://www.w3.org/ns/shacl#> .
    @prefix : <urn:ex/> .
    :a  a  :Class ;
        rdfs:label "a" .
    :b a :Class . # will fail
    """
    )

    manifest_g = Graph()
    manifest_g.parse(
        data="""
    @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
    @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
    @prefix skos: <http://www.w3.org/2004/02/skos/core#> .
    @prefix brick: <https://brickschema.org/schema/Brick#> .
    @prefix sh: <http://www.w3.org/ns/shacl#> .
    @prefix : <urn:ex/> .
    :shape a sh:NodeShape ;
        sh:targetClass :Class ;
        sh:property [ sh:path rdfs:label ; sh:minCount 1 ] .
    """
    )

    BLDG = Namespace("urn:building/")
    model = Model.create(uri=BLDG)
    model.add_graph(g)
    manifest = model.get_manifest()
    manifest.add_graph(manifest_g)

    ctx = model.validate()
    assert not ctx.valid, "Model validated but it should throw an error"


def test_get_validation_severity(clean_building_motif, shacl_engine):
    NS = Namespace("urn:ex/")
    clean_building_motif.shacl_engine = shacl_engine
    g = Graph()
    g.parse(
        data="""
    @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
    @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
    @prefix skos: <http://www.w3.org/2004/02/skos/core#> .
    @prefix brick: <https://brickschema.org/schema/Brick#> .
    @prefix sh: <http://www.w3.org/ns/shacl#> .
    @prefix : <urn:ex/> .
    :a a :Class . # will fail all shapes
    """
    )

    manifest_g = Graph()
    manifest_g.parse(
        data="""
    @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
    @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
    @prefix skos: <http://www.w3.org/2004/02/skos/core#> .
    @prefix brick: <https://brickschema.org/schema/Brick#> .
    @prefix sh: <http://www.w3.org/ns/shacl#> .
    @prefix : <urn:ex/> .
    :shape_warning a sh:NodeShape ;
        sh:targetClass :Class ;
        sh:property [
            sh:path rdfs:label ;
            sh:minCount 1  ;
            sh:severity sh:Warning ;
        ] .
    :shape_violation1 a sh:NodeShape ;
        sh:targetClass :Class ;
        sh:property [
            sh:path brick:hasPoint ;
            sh:minCount 1  ;
            sh:severity sh:Violation ;
        ] .
    :shape_violation2 a sh:NodeShape ;
        sh:targetClass :Class ;
        sh:property [
            sh:path brick:feeds ;
            sh:minCount 1  ;
            sh:severity sh:Violation ;
        ] .
    :shape_info a sh:NodeShape ;
        sh:targetClass :Class ;
        sh:property [
            sh:path brick:hasPart ;
            sh:minCount 1  ;
            sh:severity sh:Info ;
        ] .

    """
    )

    model = Model.create(uri=NS)
    model.add_graph(g)
    manifest = model.get_manifest()
    manifest.add_graph(manifest_g)

    ctx = model.validate()
    assert not ctx.valid, "Model validated but it should throw an error"

    # check that only valid severity values are accepted
    with pytest.raises(ValueError):
        reasons = ctx.get_reasons_with_severity("Nonexist")

    for severity in ["Violation", SH.Violation]:
        reasons = ctx.get_reasons_with_severity(severity)
        assert set(reasons.keys()) == {NS["a"]}
        assert len(reasons[NS["a"]]) == 2, f"Expected 2 violations, got {reasons}"

    for severity in ["Info", SH.Info]:
        reasons = ctx.get_reasons_with_severity(severity)
        assert set(reasons.keys()) == {NS["a"]}
        assert len(reasons[NS["a"]]) == 1, f"Expected 1 info, got {reasons}"

    for severity in ["Warning", SH.Warning]:
        reasons = ctx.get_reasons_with_severity(severity)
        assert set(reasons.keys()) == {NS["a"]}
        assert len(reasons[NS["a"]]) == 1, f"Expected 1 warning, got {reasons}"
