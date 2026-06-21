import csv
import io
import zipfile


class TestTrancoParsing:
    def test_filter_hu_domains_from_csv(self):
        sample_csv = "rank,domain\n1,example.hu\n2,example.com\n3,shop.hu\n4,global.shop\n"
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("top-1m.csv", sample_csv)
        buf.seek(0)

        hu_domains = []
        with zipfile.ZipFile(buf) as zf:
            for name in zf.namelist():
                with zf.open(name) as f:
                    text = f.read().decode("utf-8", errors="replace")
                    reader = csv.reader(io.StringIO(text))
                    for row in reader:
                        if len(row) >= 2:
                            domain = row[1].strip().lower()
                            if domain.endswith(".hu"):
                                hu_domains.append(domain)

        assert hu_domains == ["example.hu", "shop.hu"]

    def test_empty_zip_returns_empty_list(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("empty.csv", "")
        buf.seek(0)

        hu_domains = []
        with zipfile.ZipFile(buf) as zf:
            for name in zf.namelist():
                with zf.open(name) as f:
                    text = f.read().decode("utf-8", errors="replace")
                    reader = csv.reader(io.StringIO(text))
                    for row in reader:
                        if len(row) >= 2:
                            domain = row[1].strip().lower()
                            if domain.endswith(".hu"):
                                hu_domains.append(domain)

        assert hu_domains == []

    def test_no_hu_domains_returns_empty(self):
        sample_csv = "rank,domain\n1,example.com\n2,test.org\n"
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("top-1m.csv", sample_csv)
        buf.seek(0)

        hu_domains = []
        with zipfile.ZipFile(buf) as zf:
            for name in zf.namelist():
                with zf.open(name) as f:
                    text = f.read().decode("utf-8", errors="replace")
                    reader = csv.reader(io.StringIO(text))
                    for row in reader:
                        if len(row) >= 2:
                            domain = row[1].strip().lower()
                            if domain.endswith(".hu"):
                                hu_domains.append(domain)

        assert hu_domains == []
