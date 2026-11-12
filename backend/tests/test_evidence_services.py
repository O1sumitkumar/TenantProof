"""Evidence ingest building blocks, no HTTP: type sniffing, filename display, upload checks,
EXIF reading, metadata stripping and text extraction. Every image and PDF is built here."""

import io

import pytest
from fpdf import FPDF
from PIL import Image, PngImagePlugin

from app.services.evidence import exif, sniff, strip, text
from app.services.evidence.ingest import (
    MAX_FILES,
    MAX_NAME,
    UploadRejected,
    check,
    display_name,
)

MB = 1024 * 1024
GPS_IFD = 0x8825
EXIF_IFD = 0x8769


# --- builders -----------------------------------------------------------------------------


def make_exif(
    *, offset: str | None = "-03:00", date: str | None = "2026:08:14 21:03:12",
    gps: bool = True, orientation: int | None = None,
) -> Image.Exif:
    data = Image.Exif()
    data[0x010F] = "Apple"
    data[0x0110] = "iPhone 15"
    data[0x0131] = "Adobe Lightroom Mobile"
    if orientation is not None:
        data[0x0112] = orientation
    sub = data.get_ifd(EXIF_IFD)
    if date is not None:
        sub[0x9003] = date
    if offset is not None:
        sub[0x9011] = offset
    if gps:
        place = data.get_ifd(GPS_IFD)
        place[1] = "N"
        place[2] = (45.0, 25.0, 0.0)
        place[3] = "W"
        place[4] = (63.0, 35.0, 0.0)
    return data


def jpeg_bytes(data: Image.Exif | None = None, size: tuple[int, int] = (40, 20)) -> bytes:
    out = io.BytesIO()
    img = Image.new("RGB", size, (200, 30, 30))
    if data is None:
        img.save(out, "JPEG")
    else:
        img.save(out, "JPEG", exif=data.tobytes())
    return out.getvalue()


def png_bytes(info: PngImagePlugin.PngInfo | None = None) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (30, 10), (10, 120, 10)).save(out, "PNG", pnginfo=info)
    return out.getvalue()


def pdf_bytes(pages: list[str], producer: str | None = None) -> bytes:
    pdf = FPDF()
    if producer is not None:
        pdf.set_producer(producer)
    for body in pages:
        pdf.add_page()
        pdf.set_font("Helvetica", size=12)
        pdf.cell(text=body)
    return bytes(pdf.output())


def read_meta(data: bytes) -> exif.PhotoMeta:
    with Image.open(io.BytesIO(data)) as img:
        return exif.read_meta(img)


# --- sniff --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("data", "mime"),
    [
        (jpeg_bytes(), "image/jpeg"),
        (png_bytes(), "image/png"),
        (pdf_bytes(["hello"]), "application/pdf"),
        (b"Hello, the ceiling leaks.\nSecond line\r\n", "text/plain"),
        (b"\xef\xbb\xbfBOM text", "text/plain"),
        ("Plomberie: fuite d'eau, \u6f0f\u6c34".encode(), "text/plain"),
        (b"tab\tform\x0cfeed", "text/plain"),
    ],
)
def test_sniff_allowed_types(data, mime):
    assert sniff.sniff(data) == mime


@pytest.mark.parametrize("brand", [b"heic", b"heix", b"heim", b"heis", b"hevc", b"hevx",
                                   b"mif1", b"msf1"])
def test_sniff_heic_brands(brand):
    assert sniff.sniff(b"\x00\x00\x00\x18ftyp" + brand + b"\x00\x00\x00\x00mif1heic") == (
        "image/heic"
    )


def test_sniff_other_ftyp_brand_is_not_heic():
    # An MP4 ("isom") has the ftyp box but is not a photo; its NUL bytes make it non-text too.
    assert sniff.sniff(b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2") is None


@pytest.mark.parametrize(
    "data",
    [
        b"MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00\xff\xff",  # Windows executable
        b"",
        b"text then \x00 a NUL byte",
        b"\x00\x01\x02\x03",
        b"control \x07 bell",
        b"\x7f delete",
        b"\xff\xfe not valid utf-8",
        b"\x7fELF\x02\x01\x01",
    ],
)
def test_sniff_rejects_everything_else(data):
    assert sniff.sniff(data) is None


def test_sniff_ignores_names_and_trusts_bytes():
    # Bytes decide: a JPEG is a JPEG whatever it is called, and "MZ" never becomes a photo.
    assert sniff.sniff(jpeg_bytes()) == "image/jpeg"
    assert sniff.sniff(b"MZ" + b"\x00" * 20) is None


# --- display_name -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("photo.jpg", "photo.jpg"),
        ("../../etc/passwd.jpg", "passwd.jpg"),
        ("C:\\x\\y.jpg", "y.jpg"),
        ("a/b\\c/d.png", "d.png"),
        ("bad\x00na\x07me.pdf", "badname.pdf"),
        ("line\nbreak.txt", "linebreak.txt"),
        ("", "file"),
        (None, "file"),
        ("../", "file"),
        ("  \x01 ", "file"),
    ],
)
def test_display_name(raw, expected):
    assert display_name(raw) == expected


def test_display_name_caps_long_names():
    name = display_name("x" * 500 + ".jpg")
    assert len(name) == MAX_NAME == 120
    assert name.endswith(".jpg")  # the extension is the part worth keeping


# --- check --------------------------------------------------------------------------------


def spooled(*items: tuple[str, bytes]) -> list[tuple[str | None, io.BytesIO]]:
    return [(name, io.BytesIO(data)) for name, data in items]


def test_check_returns_uploads_with_sniffed_type_and_clean_name():
    data = jpeg_bytes()
    [up] = check(spooled(("../a/shot.png", data)), 25 * MB)
    assert (up.filename, up.mime, up.size) == ("shot.png", "image/jpeg", len(data))
    assert up.source.read() == data  # rewound for ingest


def test_check_too_big_is_413_and_names_the_file_numbers():
    big = b"a" * (MB + 1)
    with pytest.raises(UploadRejected) as err:
        check(spooled(("ok.txt", b"fine"), ("big.txt", big), ("big2.txt", big)), MB)
    assert err.value.status_code == 413
    assert len(err.value.reasons) == 2
    assert "File 2" in err.value.reasons[0] and "1 MB" in err.value.reasons[0]
    assert "File 3" in err.value.reasons[1]


def test_check_exactly_at_cap_is_allowed():
    assert len(check(spooled(("a.txt", b"a" * MB)), MB)) == 1


def test_check_wrong_type_is_415_and_names_the_file_numbers():
    with pytest.raises(UploadRejected) as err:
        check(spooled(("a.jpg", jpeg_bytes()), ("b.jpg", b"MZ\x00\x00"), ("c.txt", b"")), 25 * MB)
    assert err.value.status_code == 415
    assert len(err.value.reasons) == 2
    assert "File 2" in err.value.reasons[0]
    assert "File 3" in err.value.reasons[1]
    assert "PDF" in err.value.reasons[0]


def test_check_413_comes_before_415():
    with pytest.raises(UploadRejected) as err:
        check(spooled(("bad.exe", b"MZ\x00\x00"), ("big.txt", b"a" * (MB + 1))), MB)
    assert err.value.status_code == 413
    assert err.value.reasons == ["File 2 is larger than 1 MB"]


def test_check_more_than_max_files_is_413():
    with pytest.raises(UploadRejected) as err:
        check(spooled(*[(f"{n}.txt", b"x") for n in range(MAX_FILES + 1)]), MB)
    assert err.value.status_code == 413


def test_sniff_file_reads_only_the_head_for_binary_types_and_rewinds():
    source = io.BytesIO(jpeg_bytes())
    assert sniff.sniff_file(source, 25 * MB) == "image/jpeg"
    assert source.tell() == 0


# --- exif.read_meta -----------------------------------------------------------------------


def test_generated_input_really_carries_gps():
    # Guard for the tests below: the GPS IFD must round-trip, or "stripped" proves nothing.
    with Image.open(io.BytesIO(jpeg_bytes(make_exif()))) as img:
        assert img.getexif().get_ifd(GPS_IFD)


def test_read_meta_full():
    meta = read_meta(jpeg_bytes(make_exif()))
    assert meta.captured_at == "2026-08-14T21:03:12-03:00"
    assert meta.gps_present is True
    assert meta.device == "Apple iPhone 15"
    assert meta.software == "Adobe Lightroom Mobile"
    assert meta.as_dict() == {
        "captured_at": "2026-08-14T21:03:12-03:00", "gps_present": True,
        "device": "Apple iPhone 15", "software": "Adobe Lightroom Mobile",
    }


def test_read_meta_without_offset_has_no_zone():
    assert read_meta(jpeg_bytes(make_exif(offset=None))).captured_at == "2026-08-14T21:03:12"


def test_read_meta_ignores_a_malformed_offset():
    assert read_meta(jpeg_bytes(make_exif(offset="Z; DROP"))).captured_at == "2026-08-14T21:03:12"


@pytest.mark.parametrize("date", ["yesterday", "2026-08-14 21:03:12", "2026:13:45 99:99:99"])
def test_read_meta_malformed_date_is_none(date):
    assert read_meta(jpeg_bytes(make_exif(date=date))).captured_at is None


def test_read_meta_no_gps():
    meta = read_meta(jpeg_bytes(make_exif(gps=False)))
    assert meta.gps_present is False
    assert meta.captured_at == "2026-08-14T21:03:12-03:00"


def test_read_meta_make_not_repeated_in_model():
    data = make_exif()
    data[0x010F] = "Canon"
    data[0x0110] = "Canon EOS R6"
    assert read_meta(jpeg_bytes(data)).device == "Canon EOS R6"


def test_read_meta_without_exif_is_all_empty():
    assert read_meta(jpeg_bytes()) == exif.NO_META
    assert read_meta(png_bytes()) == exif.NO_META


def test_read_meta_cleans_and_caps_strings():
    data = make_exif()
    data[0x0131] = "Edit\x00or\x07 " + "x" * 300
    meta = read_meta(jpeg_bytes(data))
    assert meta.software is not None
    assert meta.software.startswith("Editor x")
    assert len(meta.software) == exif.MAX_TEXT
    assert not any(ord(c) < 0x20 for c in meta.software)


# --- strip.strip_image --------------------------------------------------------------------


def _assert_no_metadata(data: bytes) -> Image.Image:
    img = Image.open(io.BytesIO(data))
    img.load()
    assert len(img.getexif()) == 0
    assert not img.getexif().get_ifd(GPS_IFD)
    assert not {"exif", "icc_profile", "xmp"} & set(img.info)
    assert b"Exif" not in data and b"iPhone" not in data
    return img


def test_strip_jpeg_drops_exif_and_gps():
    original = jpeg_bytes(make_exif())
    with Image.open(io.BytesIO(original)) as src:
        assert src.getexif().get_ifd(GPS_IFD)  # precondition
        out, mime = strip.strip_image(src, "image/jpeg")
    assert mime == "image/jpeg"
    img = _assert_no_metadata(out)
    assert img.format == "JPEG"
    assert img.size == (40, 20)


def test_strip_png_stays_png_and_drops_text_chunks():
    info = PngImagePlugin.PngInfo()
    info.add_text("Author", "Secret Person")
    info.add_text("Location", "45N 63W")
    original = png_bytes(info)
    assert b"Secret Person" in original  # precondition
    with Image.open(io.BytesIO(original)) as src:
        assert "Author" in src.info or "Author" in getattr(src, "text", {})
        out, mime = strip.strip_image(src, "image/png")
    assert mime == "image/png"
    img = _assert_no_metadata(out)
    assert img.format == "PNG"
    assert img.size == (30, 10)
    assert b"Secret Person" not in out and b"Location" not in out
    assert not getattr(img, "text", {})


def test_strip_drops_icc_profile_and_xmp():
    out = io.BytesIO()
    Image.new("RGB", (8, 8)).save(out, "JPEG", icc_profile=b"\x00" * 128 + b"fake-icc")
    with Image.open(io.BytesIO(out.getvalue())) as src:
        assert "icc_profile" in src.info  # precondition
        cleaned, _ = strip.strip_image(src, "image/jpeg")
    _assert_no_metadata(cleaned)


def test_strip_applies_orientation_to_the_pixels():
    original = jpeg_bytes(make_exif(orientation=6), size=(40, 20))
    with Image.open(io.BytesIO(original)) as src:
        assert src.size == (40, 20)
        out, _ = strip.strip_image(src, "image/jpeg")
    img = _assert_no_metadata(out)  # the orientation tag is gone too
    assert img.size == (20, 40)


def test_strip_keeps_pixels_of_a_png_with_alpha():
    out = io.BytesIO()
    Image.new("RGBA", (4, 4), (1, 2, 3, 128)).save(out, "PNG")
    with Image.open(io.BytesIO(out.getvalue())) as src:
        cleaned, mime = strip.strip_image(src, "image/png")
    assert mime == "image/png"
    img = Image.open(io.BytesIO(cleaned))
    assert img.mode == "RGBA"
    assert img.getpixel((0, 0)) == (1, 2, 3, 128)


# --- text ---------------------------------------------------------------------------------


def test_read_pdf_two_pages_with_locators_and_producer():
    pdf = text.read_pdf(pdf_bytes(["Leak in kitchen", "Second page note"],
                                  producer="Acme Scanner 3"))
    pages, software = pdf.pages, pdf.software
    assert pdf.complete
    assert [p["locator"] for p in pages] == ["page 1", "page 2"]
    assert "Leak in kitchen" in pages[0]["text"]
    assert "Second page note" in pages[1]["text"]
    assert software == "Acme Scanner 3"


def test_read_pdf_without_producer_has_no_software_error():
    pdf = text.read_pdf(pdf_bytes(["only page"], producer=""))
    pages, software = pdf.pages, pdf.software
    assert len(pages) == 1
    assert software is None or isinstance(software, str)


def test_read_pdf_garbage_raises():
    with pytest.raises(Exception):  # noqa: B017, PT011 (any decoder error; ingest catches it)
        text.read_pdf(b"%PDF-1.4\nthis is not a pdf at all")


def test_read_txt_strips_the_bom_and_gives_one_message_per_line():
    pages = text.read_txt("\ufeffTenant: it leaks\nLandlord: ok".encode())
    assert pages == [{"locator": "message 1", "text": "Tenant: it leaks"},
                     {"locator": "message 2", "text": "Landlord: ok"}]


def test_read_txt_skips_blank_lines_and_drops_control_characters():
    pages = text.read_txt(b"a\tb\x00\r\n\n   \nc\x0cd\n")
    assert pages == [{"locator": "message 1", "text": "a\tb"},
                     {"locator": "message 2", "text": "c\x0cd"}]


def test_read_txt_caps_the_number_of_messages(monkeypatch):
    monkeypatch.setattr(text, "MAX_MESSAGES", 3)
    assert len(text.read_txt(b"1\n2\n3\n4\n5\n")) == 3


def test_read_pdf_parses_a_content_stream_shared_by_many_pages_once(monkeypatch):
    """A tiny PDF whose pages all point at one content stream must not cost N parses."""
    from pypdf import PageObject, PdfReader, PdfWriter

    writer = PdfWriter()
    writer.append(PdfReader(io.BytesIO(pdf_bytes(["same text"]))))
    for _ in range(9):
        writer.add_page(writer.pages[0])  # every page shares the first page's /Contents
    out = io.BytesIO()
    writer.write(out)
    calls: list[int] = []
    real = PageObject.extract_text

    def counted(self, *args, **kwargs):
        calls.append(1)
        return real(self, *args, **kwargs)

    monkeypatch.setattr(PageObject, "extract_text", counted)
    pdf = text.read_pdf(out.getvalue())
    assert len(pdf.pages) == 10 and all("same text" in p["text"] for p in pdf.pages)
    assert len(calls) == 1


def test_read_pdf_stops_at_the_time_budget(monkeypatch):
    monkeypatch.setattr(text, "PDF_SECONDS", -1.0)
    pdf = text.read_pdf(pdf_bytes(["a", "b"]))
    assert pdf.pages == [] and pdf.complete is False


def test_strip_refuses_images_over_the_pixel_limit(monkeypatch):
    monkeypatch.setattr(strip, "MAX_PIXELS", 100)
    with Image.open(io.BytesIO(jpeg_bytes())) as src, pytest.raises(strip.TooLarge):
        strip.strip_image(src, "image/jpeg")


def _software_of(value: str) -> str | None:
    data = Image.Exif()
    data[0x0131] = value
    with Image.open(io.BytesIO(jpeg_bytes(data))) as img:
        return exif.read_meta(img).software


@pytest.mark.parametrize("value", [
    "17.5", "17.5.1", "iOS 18.1", "ProCamera 17.3.8", "ProCamera 13.6.1", "Halide 2.15",
    "HDR+ 1.0.540104767zd", "G998BXXU5CVDD", "Camera", "Open Camera", "Blackmagic Camera 2.1",
])
def test_camera_apps_and_firmware_are_not_reported_as_editing_software(value):
    assert _software_of(value) is None


@pytest.mark.parametrize("value", [
    "Adobe Lightroom Mobile", "Snapseed 2.21", "Adobe Photoshop 25.0 (Macintosh)", "GIMP 2.10.36",
    "Picsart",
])
def test_editors_are_reported_as_software(value):
    assert _software_of(value) == value
