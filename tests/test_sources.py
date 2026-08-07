"""Prelievo del codice dai repository upstream: sicurezza dell'estrazione e API."""

from __future__ import annotations

import io
import shutil
import tarfile
from pathlib import Path

import pytest

from app.config import Settings
from app.exceptions import SourceUnavailable
from app.sources import extract_module, parse_github_repo

from .conftest import fixture

MANIFEST = (
    b"{'name': 'Web Responsive', 'version': '19.0.1.1.0', "
    b"'license': 'LGPL-3', 'depends': ['web', 'mail']}"
)
MODULE_FILES = {
    "web_responsive/__manifest__.py": MANIFEST,
    "web_responsive/models/main.py": b"# codice\n",
    # Un altro modulo dello stesso repository: non deve finire nell'estrazione.
    "other_module/__manifest__.py": b"{'name': 'Altro'}",
    # Gli OCA generano questi symlink per ogni addon: vanno ignorati, non rifiutati.
    "setup/web_responsive/odoo/addons/web_responsive": None,
}


def _repo_archive(tarball, **kwargs) -> bytes:
    files = {k: v for k, v in MODULE_FILES.items() if v is not None}
    symlinks = {"setup/web_responsive/odoo/addons/web_responsive": "../../../../web_responsive"}
    return tarball(files, symlinks=symlinks, **kwargs)


async def _seed_detail(services, seed_cache, series: str, name: str, page: str) -> None:
    await seed_cache(services.catalog.module_url(series, name), fixture(page))


async def _seed_web_responsive(services, seed_cache) -> None:
    """Scheda di un modulo gratuito ospitato su GitHub (OCA/web)."""
    await _seed_detail(
        services, seed_cache, "19.0", "web_responsive", "detail_web_responsive_19.html"
    )


# --------------------------------------------------------------------- unità


class TestParseGithubRepo:
    def test_url_semplice(self):
        assert parse_github_repo("https://github.com/OCA/web").url == "https://github.com/OCA/web"

    def test_url_profondo_e_senza_schema(self):
        repo = parse_github_repo("github.com/OCA/web/tree/18.0/web_responsive")
        assert (repo.owner, repo.name) == ("OCA", "web")

    def test_suffisso_git_rimosso(self):
        assert parse_github_repo("https://github.com/OCA/web.git").name == "web"

    @pytest.mark.parametrize(
        "website",
        [None, "", "https://gitlab.com/x/y", "https://github.com/OCA", "http://www.emipro.com"],
    )
    def test_sorgenti_non_supportate(self, website):
        with pytest.raises(SourceUnavailable):
            parse_github_repo(website)


class TestEstrazioneSicura:
    """`tarfile` non protegge da solo: ogni membro va validato prima di scrivere."""

    settings = Settings()

    def test_estrae_solo_il_modulo_richiesto(self, tarball, tmp_path):
        result = extract_module(
            _repo_archive(tarball), "web_responsive", tmp_path / "web_responsive",
            settings=self.settings,
        )
        estratti = sorted(str(p.relative_to(result.path)) for p in result.path.rglob("*"))
        assert estratti == ["__manifest__.py", "models", "models/main.py"]
        assert result.file_count == 2
        assert result.manifest["license"] == "LGPL-3"

    def test_symlink_di_setup_ignorati_senza_errore(self, tarball, tmp_path):
        # Se questi facessero fallire il prelievo, nessun repo OCA sarebbe prelevabile.
        result = extract_module(
            _repo_archive(tarball), "web_responsive", tmp_path / "m", settings=self.settings
        )
        assert not (result.path / "odoo").exists()

    def test_percorso_che_esce_dal_modulo_rifiutato(self, tarball, tmp_path):
        archive = tarball({"web_responsive/../../evil.py": b"pwn"})
        with pytest.raises(SourceUnavailable, match="escapes the module"):
            extract_module(archive, "web_responsive", tmp_path / "m", settings=self.settings)

    def test_symlink_dentro_il_modulo_rifiutato(self, tarball, tmp_path):
        archive = tarball(
            {"web_responsive/__manifest__.py": MANIFEST},
            symlinks={"web_responsive/leak": "/etc/passwd"},
        )
        with pytest.raises(SourceUnavailable, match="link"):
            extract_module(archive, "web_responsive", tmp_path / "m", settings=self.settings)

    def test_hardlink_dentro_il_modulo_rifiutato(self, tmp_path):
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
            info = tarfile.TarInfo("web-19.0/web_responsive/hl")
            info.type = tarfile.LNKTYPE
            info.linkname = "/etc/passwd"
            tar.addfile(info)
        with pytest.raises(SourceUnavailable, match="link"):
            extract_module(
                buffer.getvalue(), "web_responsive", tmp_path / "m", settings=self.settings
            )

    def test_tar_bomb_rifiutata(self, tarball, tmp_path):
        # 20 MB di zeri stanno in pochi KB compressi: è il rapporto a tradirla.
        archive = tarball({"web_responsive/big.bin": b"\0" * 20_000_000})
        with pytest.raises(SourceUnavailable, match="exceeds the"):
            extract_module(archive, "web_responsive", tmp_path / "m", settings=self.settings)

    def test_modulo_assente_dallarchivio(self, tarball, tmp_path):
        archive = tarball({"altro/__manifest__.py": b"{}"})
        with pytest.raises(SourceUnavailable, match="does not contain the"):
            extract_module(archive, "web_responsive", tmp_path / "m", settings=self.settings)

    def test_nessun_residuo_dopo_un_rifiuto(self, tarball, tmp_path):
        destinazione = tmp_path / "19.0" / "web_responsive"
        destinazione.parent.mkdir(parents=True)
        with pytest.raises(SourceUnavailable):
            extract_module(
                tarball({"web_responsive/../../evil": b"x"}),
                "web_responsive",
                destinazione,
                settings=self.settings,
            )
        assert list(destinazione.parent.iterdir()) == []

    def test_estrazione_precedente_sostituita(self, tarball, tmp_path):
        destinazione = tmp_path / "web_responsive"
        destinazione.mkdir()
        (destinazione / "obsoleto.py").write_text("vecchio")
        extract_module(
            _repo_archive(tarball), "web_responsive", destinazione, settings=self.settings
        )
        assert not (destinazione / "obsoleto.py").exists()


# ----------------------------------------------------------------------- API


async def test_prelievo_completo(client, app_and_services, seed_cache, tarball, serve_archive):
    _, services = app_and_services
    await _seed_web_responsive(services, seed_cache)
    richieste = serve_archive(_repo_archive(tarball))

    response = await client.post("/api/v1/sources/19.0/web_responsive")
    assert response.status_code == 200, response.text

    body = response.json()
    assert body["repo_url"] == "https://github.com/OCA/web"
    assert body["ref"] == "19.0"
    assert body["license"] == "LGPL-3"
    assert body["depends"] == ["web", "mail"]
    assert body["file_count"] == 2
    assert len(body["archive_sha256"]) == 64
    # Senza ref esplicito il branch è la serie.
    assert richieste == ["https://codeload.github.com/OCA/web/tar.gz/refs/heads/19.0"]

    elenco = (await client.get("/api/v1/sources")).json()
    assert elenco["count"] == 1
    assert elenco["items"][0]["technical_name"] == "web_responsive"

    files = (await client.get("/api/v1/sources/19.0/web_responsive/files")).json()
    assert sorted(f["path"] for f in files["files"]) == ["__manifest__.py", "models/main.py"]

    contenuto = await client.get(
        "/api/v1/sources/19.0/web_responsive/file", params={"path": "models/main.py"}
    )
    assert contenuto.json()["content"] == "# codice\n"

    assert (await client.get("/api/v1/health")).json()["sources"] == 1


async def test_ref_esplicito(client, app_and_services, seed_cache, tarball, serve_archive):
    _, services = app_and_services
    await _seed_web_responsive(services, seed_cache)
    richieste = serve_archive(_repo_archive(tarball))

    response = await client.post("/api/v1/sources/19.0/web_responsive", params={"ref": "master"})
    assert response.status_code == 200
    assert response.json()["ref"] == "master"
    assert richieste[0].endswith("/refs/heads/master")


async def test_modulo_a_pagamento_rifiutato(client, app_and_services, seed_cache, serve_archive):
    _, services = app_and_services
    await _seed_detail(
        services, seed_cache, "18.0", "common_connector_library",
        "detail_common_connector_library_18.html",
    )
    serve_archive(b"")

    response = await client.post("/api/v1/sources/18.0/common_connector_library")
    assert response.status_code == 400
    assert "paid module" in response.json()["detail"]


@pytest.mark.parametrize(
    ("files", "symlinks", "atteso"),
    [
        ({"web_responsive/../../evil": b"x"}, None, "escapes the module"),
        ({"web_responsive/__manifest__.py": MANIFEST}, {"web_responsive/l": "/etc/passwd"}, "link"),
        ({"altro/__manifest__.py": b"{}"}, None, "does not contain the"),
    ],
)
async def test_archivi_ostili_rifiutati_dallapi(
    client, app_and_services, seed_cache, tarball, serve_archive, files, symlinks, atteso
):
    _, services = app_and_services
    await _seed_web_responsive(services, seed_cache)
    serve_archive(tarball(files, symlinks=symlinks))

    response = await client.post("/api/v1/sources/19.0/web_responsive")
    assert response.status_code == 400
    assert atteso in response.json()["detail"]


async def test_branch_inesistente(client, app_and_services, seed_cache, serve_archive):
    _, services = app_and_services
    await _seed_web_responsive(services, seed_cache)
    serve_archive(b"Not Found", status=404)

    response = await client.post("/api/v1/sources/19.0/web_responsive", params={"ref": "assente"})
    assert response.status_code == 400
    assert "assente" in response.json()["detail"]


async def test_lettura_di_un_modulo_mai_prelevato(client):
    response = await client.get("/api/v1/sources/19.0/web_responsive/files")
    assert response.status_code == 404
    assert "has not been fetched yet" in response.json()["detail"]


async def test_path_traversal_in_lettura(
    client, app_and_services, seed_cache, tarball, serve_archive
):
    _, services = app_and_services
    await _seed_web_responsive(services, seed_cache)
    serve_archive(_repo_archive(tarball))
    await client.post("/api/v1/sources/19.0/web_responsive")

    response = await client.get(
        "/api/v1/sources/19.0/web_responsive/file", params={"path": "../../../../etc/passwd"}
    )
    assert response.status_code == 400
    assert "escapes the module directory" in response.json()["detail"]


async def test_prelievo_idempotente(
    client, app_and_services, seed_cache, tarball, serve_archive
):
    _, services = app_and_services
    await _seed_web_responsive(services, seed_cache)
    richieste = serve_archive(_repo_archive(tarball))

    await client.post("/api/v1/sources/19.0/web_responsive")
    await client.post("/api/v1/sources/19.0/web_responsive")
    assert len(richieste) == 1, "il secondo prelievo doveva usare quanto già su disco"

    await client.post("/api/v1/sources/19.0/web_responsive", params={"force": "true"})
    assert len(richieste) == 2

    assert (await client.get("/api/v1/sources")).json()["count"] == 1


async def test_record_orfano_ignorato(
    client, app_and_services, seed_cache, tarball, serve_archive
):
    """Se la cartella sparisce, il record in tabella non deve più comparire."""
    _, services = app_and_services
    await _seed_web_responsive(services, seed_cache)
    serve_archive(_repo_archive(tarball))
    prelevato = (await client.post("/api/v1/sources/19.0/web_responsive")).json()

    shutil.rmtree(Path(prelevato["path"]))

    assert (await client.get("/api/v1/sources")).json()["count"] == 0
    assert (await client.get("/api/v1/sources/19.0/web_responsive/files")).status_code == 404
