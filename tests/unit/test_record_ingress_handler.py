import io
from pathlib import Path

from buildingmotif.ingresses.base import Record, RecordIngressHandler
from buildingmotif.ingresses.csvingress import CSVIngress


def test_ingress_dump_load(bm, tmp_path: Path):
    records = [
        Record("a", {"a": 1, "b": 2}),
        Record("b", {"b": 1, "a": 2}),
    ]

    output_file = tmp_path / "output.json"

    ingress_handler_1 = RecordIngressHandler.__new__(RecordIngressHandler)
    ingress_handler_1.records = records
    ingress_handler_1.dump(output_file)

    ingress_handler_2 = RecordIngressHandler.load(output_file)
    ingress_records = ingress_handler_2.records

    assert ingress_records == records


def test_csv_ingress_closes_file_after_read(monkeypatch):
    opened_streams = []

    class TrackingStringIO(io.StringIO):
        def close(self):
            opened_streams.append(("closed", self.closed))
            super().close()

    def fake_open(*_args, **_kwargs):
        stream = TrackingStringIO("a,b\n1,2\n")
        opened_streams.append(stream)
        return stream

    monkeypatch.setattr("builtins.open", fake_open)

    ingress = CSVIngress(Path("test.csv"))

    assert ingress.records == [Record("test.csv", {"a": "1", "b": "2"})]
    assert len(opened_streams) == 2
    assert isinstance(opened_streams[0], TrackingStringIO)
    assert opened_streams[0].closed
