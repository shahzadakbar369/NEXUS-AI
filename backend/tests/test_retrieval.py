# pyrefly: ignore[missing-import]
import fitz
# pyrefly: ignore[missing-import]
import pytest   

from app.services import document_processor as dp
from app.services.vector_store import VectorStore
from tests.conftest import FakeEmbedder


def make_pdf(path, pages):
    doc = fitz.open()
    for text in pages:
        page = doc.new_page()
        page.insert_textbox(fitz.Rect(50, 50, 550, 800), text)
    doc.save(path)
    doc.close()


def test_chunking_overlaps_and_keeps_pages():
    pages = [dp.Page(1, "alpha " * 400), dp.Page(2, "beta " * 50)]
    chunks = dp.chunk_pages(pages, size=500, overlap=100)
    assert {c["page"] for c in chunks} == {1, 2}
    assert all(len(c["text"]) <= 500 for c in chunks)
    p1 = [c["text"] for c in chunks if c["page"] == 1]
    assert len(p1) > 1 and p1[0][-50:].strip() in pages[0].text


def test_extract_pdf_with_pages(tmp_path):
    p = tmp_path / "a.pdf"
    make_pdf(p, ["The capital of France is Paris.", "Photosynthesis converts light into chemical energy."])
    pages = dp.extract_pdf(p)
    assert [pg.page for pg in pages] == [1, 2]
    assert "Paris" in pages[0].text


def test_empty_pdf_rejected(tmp_path):
    p = tmp_path / "empty.pdf"
    make_pdf(p, [""])
    with pytest.raises(dp.DocumentError, match="scanned"):
        dp.extract_pdf(p)


def test_corrupt_pdf_rejected(tmp_path):
    p = tmp_path / "bad.pdf"
    p.write_bytes(b"%PDF-1.4 garbage garbage")
    with pytest.raises(dp.DocumentError):
        dp.extract_pdf(p)


def test_detect_kind():
    assert dp.detect_kind("x.pdf", b"%PDF-1.7") == "pdf"
    assert dp.detect_kind("x.png", b"\x89PNG\r\n") == "image"
    with pytest.raises(dp.DocumentError):
        dp.detect_kind("x.pdf", b"MZ\x90\x00")  # an .exe renamed to .pdf
    with pytest.raises(dp.DocumentError):
        dp.detect_kind("x.docx", b"PK")


def test_retrieval_scoped_and_ranked(tmp_path):
    store = VectorStore(tmp_path, FakeEmbedder())
    store.add_document("doc1", "france.pdf", [
        {"page": 1, "text": "Paris is the capital city of France."},
        {"page": 2, "text": "French cuisine includes croissants and cheese."},
    ])
    store.add_document("doc2", "biology.pdf", [{"page": 7, "text": "Photosynthesis happens in chloroplasts of plants."}])

    hits = store.search("what is the capital city of france", ["doc1", "doc2"], top_k=3, min_score=0.2)
    assert hits[0]["filename"] == "france.pdf" and hits[0]["page"] == 1

    # Only searches the requested documents (chat scoping)
    hits = store.search("photosynthesis chloroplasts plants", ["doc1"], top_k=3, min_score=0.2)
    assert all(h["document_id"] == "doc1" for h in hits)


def test_unrelated_query_returns_nothing(tmp_path):
    store = VectorStore(tmp_path, FakeEmbedder())
    store.add_document("doc1", "france.pdf", [{"page": 1, "text": "Paris is the capital city of France."}])
    assert store.search("quantum chromodynamics gluons", ["doc1"], top_k=3, min_score=0.3) == []


def test_index_persists_and_delete(tmp_path):
    VectorStore(tmp_path, FakeEmbedder()).add_document("doc1", "a.pdf", [{"page": 1, "text": "persistent vectors here"}])
    store2 = VectorStore(tmp_path, FakeEmbedder())  # simulates a restart
    assert store2.search("persistent vectors", ["doc1"], 3, 0.2)
    store2.delete_document("doc1")
    assert store2.search("persistent vectors", ["doc1"], 3, 0.2) == []
