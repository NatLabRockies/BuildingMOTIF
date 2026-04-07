import os
import tempfile
import types
from typing import ClassVar, List, Tuple

import rdflib

from buildingmotif import BuildingMOTIF
from buildingmotif.dataclasses.library import Library


class FakeOntoEnv:
    instances: ClassVar[List["FakeOntoEnv"]] = []

    def __init__(self, graph_store, temporary=True, **_kwargs) -> None:
        self.graph_store = graph_store
        self.temporary = temporary
        self.last_graph_name = None
        self.closed = False
        type(self).instances.append(self)

    def get_dependencies(
        self,
        graph: rdflib.Graph,
        graph_name=None,
        recursion_depth=-1,
        fetch_missing=False,
    ) -> Tuple[rdflib.Graph, List[str]]:
        del fetch_missing
        self.last_graph_name = graph_name

        resolved = rdflib.Graph()
        seen = set()
        closure = []

        def walk(current_graph: rdflib.Graph, depth: int) -> None:
            nonlocal resolved
            if depth == 0:
                return
            next_depth = depth - 1 if depth > 0 else depth
            for dependency in current_graph.objects(predicate=rdflib.OWL.imports):
                dependency_iri = str(dependency)
                if dependency_iri in seen:
                    continue
                seen.add(dependency_iri)
                closure.append(dependency_iri)
                dep_graph = self.graph_store.get_graph(dependency_iri)
                resolved += dep_graph
                walk(dep_graph, next_depth)

        walk(graph, recursion_depth)
        return resolved, closure

    def get_graph(self, uri):
        return self.graph_store.get_graph(uri)

    def missing_imports(self, uri=None):
        if uri is None:
            missing = set()
            for graph_id in self.graph_store.graph_ids():
                missing.update(self.missing_imports(graph_id))
            return sorted(missing)

        if isinstance(uri, rdflib.Graph):
            root_graph = uri
        else:
            root_graph = self.graph_store.get_graph(uri)

        missing = set()
        seen = set()

        def walk(current_graph: rdflib.Graph):
            for dependency in current_graph.objects(predicate=rdflib.OWL.imports):
                dependency_iri = str(dependency)
                if dependency_iri in seen:
                    continue
                seen.add(dependency_iri)
                try:
                    dep_graph = self.graph_store.get_graph(dependency_iri)
                except Exception:
                    missing.add(dependency_iri)
                    continue
                walk(dep_graph)

        walk(root_graph)
        return sorted(missing)

    def close(self):
        self.closed = True
        return None


def test_shape_collection_resolve_imports_with_ontoenv(monkeypatch):
    import buildingmotif.dependency_resolver as resolver_mod

    real_import_module = resolver_mod.importlib.import_module

    def fake_import_module(name):
        if name == "ontoenv":
            return types.SimpleNamespace(OntoEnv=FakeOntoEnv)
        return real_import_module(name)

    monkeypatch.setattr(resolver_mod.importlib, "import_module", fake_import_module)

    BuildingMOTIF.clean()
    with tempfile.TemporaryDirectory() as tempdir:
        uri = f"sqlite:///{os.path.join(tempdir, 'temp.db')}"
        bm = BuildingMOTIF(uri)
        bm.setup_tables()

        Library.load(ontology_graph="tests/unit/fixtures/Brick.ttl")
        Library.load(ontology_graph="constraints/constraints.ttl")
        lib = Library.load(ontology_graph="tests/unit/fixtures/shapes/import_test.ttl")
        sc = lib.get_shape_collection()

        resolved = sc.resolve_imports()

        assert len(resolved.graph) > len(sc.graph)
        assert (
            bm.ontology_resolver.env.last_graph_name
            == "urn:medium-office-brick-constraints/"
        )
        assert "https://brickschema.org/schema/1.4/Brick" in (
            bm.ontology_resolver.graph_store.graph_ids()
        )

        bm.session.commit()
        bm.close()
        BuildingMOTIF.clean()


def test_buildingmotif_lists_closure_with_ontoenv(monkeypatch):
    import buildingmotif.dependency_resolver as resolver_mod

    real_import_module = resolver_mod.importlib.import_module

    def fake_import_module(name):
        if name == "ontoenv":
            return types.SimpleNamespace(OntoEnv=FakeOntoEnv)
        return real_import_module(name)

    monkeypatch.setattr(resolver_mod.importlib, "import_module", fake_import_module)

    BuildingMOTIF.clean()
    with tempfile.TemporaryDirectory() as tempdir:
        uri = f"sqlite:///{os.path.join(tempdir, 'temp.db')}"
        bm = BuildingMOTIF(uri)
        bm.setup_tables()

        Library.load(ontology_graph="tests/unit/fixtures/Brick.ttl")
        lib = Library.load(ontology_graph="tests/unit/fixtures/shapes/shape2.ttl")

        assert bm.list_ontology_closure(library=lib) == [
            "https://brickschema.org/schema/1.4/Brick"
        ]

        bm.session.commit()
        bm.close()
        BuildingMOTIF.clean()


def test_shape_collection_resolve_imports_skips_embedded_ontologies(monkeypatch):
    import buildingmotif.dependency_resolver as resolver_mod

    real_import_module = resolver_mod.importlib.import_module

    def fake_import_module(name):
        if name == "ontoenv":
            return types.SimpleNamespace(OntoEnv=FakeOntoEnv)
        return real_import_module(name)

    monkeypatch.setattr(resolver_mod.importlib, "import_module", fake_import_module)

    BuildingMOTIF.clean()
    with tempfile.TemporaryDirectory() as tempdir:
        uri = f"sqlite:///{os.path.join(tempdir, 'temp.db')}"
        bm = BuildingMOTIF(uri)
        bm.setup_tables()

        dep_graph = rdflib.Graph().parse(
            data="""
            @prefix owl: <http://www.w3.org/2002/07/owl#> .
            <urn:dep/> a owl:Ontology .
            <urn:dep/s> <urn:p> <urn:o> .
            """,
            format="ttl",
        )
        Library.load(ontology_graph=dep_graph, infer_templates=False)

        root_graph = rdflib.Graph().parse(
            data="""
            @prefix owl: <http://www.w3.org/2002/07/owl#> .
            <urn:root/> a owl:Ontology ;
                owl:imports <urn:dep/> .
            """,
            format="ttl",
        )
        lib = Library.load(ontology_graph=root_graph, infer_templates=False)
        sc = lib.get_shape_collection()
        sc.graph += dep_graph

        resolved = sc.resolve_imports()

        assert len(resolved.graph) == len(sc.graph)
        assert set(resolved.graph) == set(sc.graph)

        bm.close()
        BuildingMOTIF.clean()


def test_buildingmotif_list_missing_ontologies_reports_direct_missing_imports(
    monkeypatch,
):
    import buildingmotif.dependency_resolver as resolver_mod

    real_import_module = resolver_mod.importlib.import_module

    def fake_import_module(name):
        if name == "ontoenv":
            return types.SimpleNamespace(OntoEnv=FakeOntoEnv)
        return real_import_module(name)

    monkeypatch.setattr(resolver_mod.importlib, "import_module", fake_import_module)

    BuildingMOTIF.clean()
    with tempfile.TemporaryDirectory() as tempdir:
        uri = f"sqlite:///{os.path.join(tempdir, 'temp.db')}"
        bm = BuildingMOTIF(uri)
        bm.setup_tables()

        missing_graph = rdflib.Graph().parse(
            data="""
            @prefix owl: <http://www.w3.org/2002/07/owl#> .
            <urn:missing-library/> a owl:Ontology ;
                owl:imports <urn:missing/lib> .
            """,
            format="ttl",
        )
        missing_lib = Library.load(ontology_graph=missing_graph, infer_templates=False)

        assert bm.list_missing_ontologies(library=missing_lib) == ["urn:missing/lib"]

        bm.session.commit()
        bm.close()
        BuildingMOTIF.clean()


def test_buildingmotif_list_missing_ontologies_reports_transitive_missing_imports(
    monkeypatch,
):
    import buildingmotif.dependency_resolver as resolver_mod

    real_import_module = resolver_mod.importlib.import_module

    def fake_import_module(name):
        if name == "ontoenv":
            return types.SimpleNamespace(OntoEnv=FakeOntoEnv)
        return real_import_module(name)

    monkeypatch.setattr(resolver_mod.importlib, "import_module", fake_import_module)

    BuildingMOTIF.clean()
    with tempfile.TemporaryDirectory() as tempdir:
        uri = f"sqlite:///{os.path.join(tempdir, 'temp.db')}"
        bm = BuildingMOTIF(uri)
        bm.setup_tables()

        b_graph = rdflib.Graph().parse(
            data="""
            @prefix owl: <http://www.w3.org/2002/07/owl#> .
            <urn:b/> a owl:Ontology ;
                owl:imports <urn:c/> .
            """,
            format="ttl",
        )
        a_graph = rdflib.Graph().parse(
            data="""
            @prefix owl: <http://www.w3.org/2002/07/owl#> .
            <urn:a/> a owl:Ontology ;
                owl:imports <urn:b/> .
            """,
            format="ttl",
        )

        b_lib = Library.load(ontology_graph=b_graph, infer_templates=False)
        a_lib = Library.load(ontology_graph=a_graph, infer_templates=False)

        assert bm.list_missing_ontologies(library=a_lib) == ["urn:c/"]
        assert bm.list_missing_ontologies(library=b_lib) == ["urn:c/"]

        bm.session.commit()
        bm.close()
        BuildingMOTIF.clean()


def test_register_ontology_invalidates_cached_ontoenv(monkeypatch):
    import buildingmotif.dependency_resolver as resolver_mod

    FakeOntoEnv.instances = []
    real_import_module = resolver_mod.importlib.import_module

    def fake_import_module(name):
        if name == "ontoenv":
            return types.SimpleNamespace(OntoEnv=FakeOntoEnv)
        return real_import_module(name)

    monkeypatch.setattr(resolver_mod.importlib, "import_module", fake_import_module)

    BuildingMOTIF.clean()
    with tempfile.TemporaryDirectory() as tempdir:
        uri = f"sqlite:///{os.path.join(tempdir, 'temp.db')}"
        bm = BuildingMOTIF(uri)
        bm.setup_tables()

        env1 = bm.ontology_resolver.env
        Library.load(ontology_graph="tests/unit/fixtures/Brick.ttl")
        env2 = bm.ontology_resolver.env

        assert env2 is not env1
        assert env1.closed is True
        assert len(FakeOntoEnv.instances) == 2

        bm.close()
        BuildingMOTIF.clean()
