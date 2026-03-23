#!/usr/bin/env python3
"""Extract bibliography entries from a LaTeX proposal and download full texts.

This script is intentionally tailored to the bibliography style used in
docs/proposals/proposal_updated_2.tex, but it also works on similar inline
thebibliography blocks.
"""

from __future__ import annotations

import argparse
import csv
import difflib
import json
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup


USER_AGENT = "CodexReferenceDownloader/1.0 (project-proposal audit)"
REQUEST_TIMEOUT = 30
MANUAL_METADATA_OVERRIDES = {
    "dumitrescu2003sp": {
        "doi": "10.1109/TSP.2003.812753",
        "matched_title": "Detection of LSB steganography via sample pair analysis",
        "note": "Correct DOI for the cited IEEE Transactions on Signal Processing journal paper.",
    }
}

MANUAL_FULLTEXT_OVERRIDES = {
    "petitcolas1999": {
        "url": "https://www.petitcolas.net/fabien/publications/ieee99-infohiding.pdf",
        "note": "Author-hosted PDF from Fabien Petitcolas publications page.",
    },
    "hussain2018": {
        "url": "https://muhammetbaykara.com/wp-content/uploads/2018/10/ymhgunduz_stego.pdf",
        "note": "Author-available PDF located via exact-title search.",
    },
    "fridrich2012srm": {
        "url": "https://ws2.binghamton.edu/fridrich/Research/TIFS2012-SRM.pdf",
        "note": "Author-hosted PDF from Jessica Fridrich publications page.",
    },
    "kodovsky2012ec": {
        "url": "https://ws2.binghamton.edu/fridrich/Research/ensemble-doubleColumn.pdf",
        "note": "Author-hosted PDF from Jessica Fridrich publications page.",
    },
    "fridrich2001lsb": {
        "url": "https://ws2.binghamton.edu/fridrich/Research/acm_2001_03.pdf",
        "note": "Author-hosted PDF from Jessica Fridrich publications page.",
    },
    "holub2015dctr": {
        "url": "https://ws2.binghamton.edu/fridrich/Research/DCTR.pdf",
        "note": "Author-hosted PDF from Jessica Fridrich publications page.",
    },
    "fridrich2003calib": {
        "url": "https://ws2.binghamton.edu/fridrich/Research/jpeg01.pdf",
        "note": "Author-hosted PDF from Jessica Fridrich publications page.",
    },
    "boroumand2019srnet": {
        "url": "https://ws2.binghamton.edu/fridrich/Research/SRNet.pdf",
        "note": "Author-hosted PDF from Jessica Fridrich publications page.",
    },
    "zhang2011fsim": {
        "url": "http://www4.comp.polyu.edu.hk/~cslzhang/paper/PCG_IQA.pdf",
        "note": "Author-hosted PDF from Lin Zhang's page.",
    },
    "mittal2012brisque": {
        "url": "https://live.ece.utexas.edu/publications/2012/TIP%20BRISQUE.pdf",
        "note": "Author-hosted PDF from the LIVE Lab site.",
    },
}


def log(message: str) -> None:
    print(message, file=sys.stderr)


def normalize_title(value: str) -> str:
    lowered = value.lower()
    lowered = lowered.replace("\\alpha", "alpha")
    lowered = lowered.replace("\\", "")
    lowered = re.sub(r"[^a-z0-9]+", " ", lowered)
    return re.sub(r"\s+", " ", lowered).strip()


def latex_to_text(value: str) -> str:
    text = value
    replacements = {
        r"\'{e}": "e",
        r"\'{E}": "E",
        r"\'{y}": "y",
        r"\'{Y}": "Y",
        r"\'{a}": "a",
        r"\'{A}": "A",
        r"\'{i}": "i",
        r"\'{I}": "I",
        r"\'{o}": "o",
        r"\'{O}": "O",
        r"\'{u}": "u",
        r"\'{U}": "U",
        r"\v{s}": "s",
        r"\v{S}": "S",
        r"\v{z}": "z",
        r"\v{Z}": "Z",
        r"\v{c}": "c",
        r"\v{C}": "C",
        r"\alpha": "alpha",
        r"\&": "&",
        r"\%": "%",
        r"\_": "_",
        r"\texttt": "",
        r"\textit": "",
        r"\mathrm": "",
        r"\emph": "",
        r"\Proc.": "Proc.",
        r"\ ": " ",
        "~": " ",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = re.sub(r"\\url\{([^}]+)\}", r"\1", text)
    text = re.sub(r"\\[a-zA-Z]+\{([^}]*)\}", r"\1", text)
    text = re.sub(r"[{}]", "", text)
    text = text.replace("``", '"').replace("''", '"')
    text = re.sub(r"\s+", " ", text).strip()
    return text


@dataclass
class Reference:
    key: str
    raw_citation: str
    clean_citation: str
    title: str
    authors: str
    year: str
    doi: str = ""
    arxiv_id: str = ""
    explicit_url: str = ""
    reference_type: str = "scholarly"


@dataclass
class Resolution:
    key: str
    title: str
    year: str
    authors: str
    citation: str
    original_doi: str = ""
    resolved_doi: str = ""
    arxiv_id: str = ""
    openalex_id: str = ""
    matched_title: str = ""
    match_score: float = 0.0
    landing_url: str = ""
    fulltext_url: str = ""
    file_path: str = ""
    file_type: str = ""
    status: str = "unresolved"
    note: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class Downloader:
    def __init__(self, tex_path: Path, output_dir: Path) -> None:
        self.tex_path = tex_path
        self.output_dir = output_dir
        self.files_dir = output_dir / "files"
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})

    def run(self) -> list[Resolution]:
        refs = self.extract_references()
        self.files_dir.mkdir(parents=True, exist_ok=True)
        parsed_path = self.output_dir / "parsed_references.json"
        parsed_path.parent.mkdir(parents=True, exist_ok=True)
        parsed_path.write_text(
            json.dumps([asdict(ref) for ref in refs], indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        results: list[Resolution] = []
        for index, ref in enumerate(refs, start=1):
            log(f"[{index}/{len(refs)}] Resolving {ref.key}: {ref.title}")
            resolution = self.resolve_reference(ref)
            if resolution.fulltext_url:
                self.download_resolution(ref, resolution)
            results.append(resolution)
            time.sleep(0.2)

        self.write_reports(results)
        return results

    def extract_references(self) -> list[Reference]:
        content = self.tex_path.read_text(encoding="utf-8")
        match = re.search(
            r"\\begin\{thebibliography\}\{[^}]*\}(.*?)\\end\{thebibliography\}",
            content,
            flags=re.S,
        )
        if not match:
            raise ValueError(f"No thebibliography block found in {self.tex_path}")

        block = match.group(1).strip()
        chunks = re.split(r"(?=\\bibitem\{)", block)
        refs: list[Reference] = []
        for chunk in chunks:
            chunk = chunk.strip()
            if not chunk.startswith(r"\bibitem{"):
                continue
            key_match = re.match(r"\\bibitem\{([^}]+)\}\s*(.*)", chunk, flags=re.S)
            if not key_match:
                continue
            key = key_match.group(1).strip()
            raw = re.sub(r"\s+", " ", key_match.group(2)).strip()
            clean = latex_to_text(raw)
            title_match = re.search(r'"([^"]+)"', clean)
            title = title_match.group(1).strip().rstrip(".,") if title_match else clean
            authors = clean.split('"')[0].strip().rstrip(",")
            year_matches = [match.group(0) for match in re.finditer(r"\b(?:19|20)\d{2}\b", clean)]
            year = year_matches[-1] if year_matches else ""
            doi_match = re.search(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", clean, flags=re.I)
            arxiv_match = re.search(r"arXiv:(\d{4}\.\d{4,5})", clean, flags=re.I)
            url_match = re.search(r"https?://\S+", clean)
            ref_type = "artifact" if "github.com" in clean.lower() else "scholarly"
            refs.append(
                Reference(
                    key=key,
                    raw_citation=raw,
                    clean_citation=clean,
                    title=title,
                    authors=authors,
                    year=year,
                    doi=doi_match.group(0) if doi_match else "",
                    arxiv_id=arxiv_match.group(1) if arxiv_match else "",
                    explicit_url=url_match.group(0).rstrip(".,") if url_match else "",
                    reference_type=ref_type,
                )
            )
        return refs

    def resolve_reference(self, ref: Reference) -> Resolution:
        resolution = Resolution(
            key=ref.key,
            title=ref.title,
            year=ref.year,
            authors=ref.authors,
            citation=ref.clean_citation,
            original_doi=ref.doi,
            arxiv_id=ref.arxiv_id,
        )

        metadata_override = MANUAL_METADATA_OVERRIDES.get(ref.key)
        if metadata_override:
            resolution.resolved_doi = metadata_override.get("doi", "")
            resolution.matched_title = metadata_override.get("matched_title", ref.title)
            resolution.match_score = 1.0

        existing_file = self.find_existing_download(ref.key)
        if existing_file:
            resolution.file_path = str(existing_file)
            resolution.file_type = existing_file.suffix.lstrip(".")
            resolution.status = "downloaded"
            resolution.note = "Using manually supplied local file already present in the references folder."
            return resolution

        override = MANUAL_FULLTEXT_OVERRIDES.get(ref.key)
        if override:
            resolution.landing_url = override["url"]
            resolution.fulltext_url = override["url"]
            resolution.file_type = self.infer_file_type(override["url"])
            resolution.status = "resolved"
            resolution.note = override["note"]
            return resolution

        if ref.arxiv_id:
            resolution.fulltext_url = f"https://arxiv.org/pdf/{ref.arxiv_id}.pdf"
            resolution.landing_url = f"https://arxiv.org/abs/{ref.arxiv_id}"
            resolution.file_type = "pdf"
            resolution.status = "resolved"
            resolution.note = "Direct arXiv match from citation."
            return resolution

        arxiv_match = self.lookup_arxiv(ref)
        if arxiv_match:
            resolution.arxiv_id = arxiv_match["arxiv_id"]
            resolution.landing_url = arxiv_match["landing_url"]
            resolution.fulltext_url = arxiv_match["pdf_url"]
            resolution.file_type = "pdf"
            resolution.status = "resolved"
            resolution.note = "Exact-title arXiv preprint found for the cited work."
            return resolution

        if ref.reference_type == "artifact" and ref.explicit_url:
            archive_url = self.github_archive_url(ref.explicit_url)
            resolution.landing_url = ref.explicit_url
            resolution.fulltext_url = archive_url or ref.explicit_url
            resolution.file_type = "zip" if archive_url else "html"
            resolution.status = "resolved"
            resolution.note = "Software artifact; repository snapshot used instead of paper PDF."
            return resolution

        crossref = self.lookup_crossref(ref)
        if crossref and not resolution.resolved_doi:
            resolution.matched_title = crossref.get("title", "")
            resolution.match_score = crossref.get("score", 0.0)
            resolution.resolved_doi = crossref.get("doi", "")
            resolution.metadata["crossref"] = crossref

        effective_doi = resolution.resolved_doi or ref.doi
        elsevier_url = self.elsevier_fulltext_url(effective_doi)
        if elsevier_url:
            resolution.landing_url = f"https://doi.org/{effective_doi}"
            resolution.fulltext_url = elsevier_url
            resolution.file_type = "xml"
            resolution.status = "resolved"
            resolution.note = "Full-text XML available from the Elsevier content API."
            return resolution

        openalex = self.lookup_openalex(ref, resolution.resolved_doi)
        if openalex:
            resolution.openalex_id = openalex.get("id", "")
            resolution.metadata["openalex"] = openalex
            resolution.matched_title = openalex.get("display_name", resolution.matched_title)
            resolution.landing_url = self.best_landing_url(openalex) or resolution.landing_url
            pdf_url = self.best_pdf_url(openalex)
            if pdf_url:
                resolution.fulltext_url = pdf_url
                resolution.file_type = "pdf"
                resolution.status = "resolved"
                resolution.note = "Open-access PDF found via OpenAlex."
                return resolution

        if resolution.landing_url:
            discovered = self.discover_fulltext_url(resolution.landing_url)
            if discovered:
                resolution.fulltext_url = discovered
                resolution.file_type = self.infer_file_type(discovered)
                resolution.status = "resolved"
                resolution.note = "Full text discovered from landing page metadata."
                return resolution

        if ref.explicit_url:
            resolution.landing_url = resolution.landing_url or ref.explicit_url
            discovered = self.discover_fulltext_url(ref.explicit_url)
            if discovered:
                resolution.fulltext_url = discovered
                resolution.file_type = self.infer_file_type(discovered)
                resolution.status = "resolved"
                resolution.note = "Full text discovered from citation URL."
                return resolution

        resolution.status = "unresolved"
        resolution.note = "No downloadable full text found automatically."
        return resolution

    def find_existing_download(self, key: str) -> Path | None:
        for suffix in (".pdf", ".xml", ".html", ".zip"):
            candidate = self.files_dir / f"{key}{suffix}"
            if candidate.exists():
                return candidate
        return None

    def elsevier_fulltext_url(self, doi: str) -> str:
        if not doi:
            return ""
        normalized = doi.lower()
        if not normalized.startswith("10.1016/"):
            return ""
        return f"https://api.elsevier.com/content/article/doi/{doi}"

    def lookup_arxiv(self, ref: Reference) -> dict[str, str] | None:
        if ref.reference_type != "scholarly":
            return None

        try:
            response = self.session.get(
                "https://export.arxiv.org/api/query",
                params={"search_query": f'ti:"{ref.title}"', "start": 0, "max_results": 3},
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
        except requests.RequestException:
            return None

        entries = re.findall(r"<entry>(.*?)</entry>", response.text, flags=re.S)
        target = normalize_title(ref.title)
        for entry in entries:
            title_match = re.search(r"<title>\s*(.*?)\s*</title>", entry, flags=re.S)
            id_match = re.search(r"<id>\s*http://arxiv.org/abs/([^<]+)\s*</id>", entry)
            if not title_match or not id_match:
                continue
            candidate_title = re.sub(r"\s+", " ", title_match.group(1)).strip()
            similarity = difflib.SequenceMatcher(
                a=target,
                b=normalize_title(candidate_title),
            ).ratio()
            if similarity < 0.92:
                continue
            arxiv_id = id_match.group(1)
            versionless_id = arxiv_id.split("v", 1)[0]
            return {
                "arxiv_id": versionless_id,
                "landing_url": f"https://arxiv.org/abs/{versionless_id}",
                "pdf_url": f"https://arxiv.org/pdf/{versionless_id}.pdf",
            }
        return None

    def lookup_crossref(self, ref: Reference) -> dict[str, Any] | None:
        if ref.doi:
            return {
                "doi": ref.doi,
                "title": ref.title,
                "score": 1.0,
                "source": "citation",
            }

        params = {
            "query.title": ref.title,
            "rows": 5,
            "select": "DOI,title,published-print,published-online,published,author,URL",
        }
        response = self.session.get(
            "https://api.crossref.org/works",
            params=params,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        items = response.json().get("message", {}).get("items", [])
        best: dict[str, Any] | None = None
        best_score = 0.0
        target = normalize_title(ref.title)
        for item in items:
            titles = item.get("title") or []
            if not titles:
                continue
            candidate_title = titles[0]
            similarity = difflib.SequenceMatcher(
                a=target,
                b=normalize_title(candidate_title),
            ).ratio()
            year_candidates = self.extract_years_from_crossref(item)
            year_bonus = 0.05 if ref.year and ref.year in year_candidates else 0.0
            score = similarity + year_bonus
            if score > best_score:
                best_score = score
                best = {
                    "doi": item.get("DOI", ""),
                    "title": candidate_title,
                    "score": round(score, 4),
                    "url": item.get("URL", ""),
                }
        return best if best_score >= 0.75 else None

    def extract_years_from_crossref(self, item: dict[str, Any]) -> set[str]:
        years: set[str] = set()
        for key in ("published-print", "published-online", "published"):
            parts = item.get(key, {}).get("date-parts", [])
            if parts and parts[0]:
                years.add(str(parts[0][0]))
        return years

    def lookup_openalex(self, ref: Reference, doi: str) -> dict[str, Any] | None:
        urls = []
        if doi:
            encoded = quote(f"https://doi.org/{doi}", safe="")
            urls.append(f"https://api.openalex.org/works/{encoded}")
        title_query = quote(ref.title)
        urls.append(f"https://api.openalex.org/works?search={title_query}&per-page=5")

        target = normalize_title(ref.title)
        for url in urls:
            response = self.session.get(url, timeout=REQUEST_TIMEOUT)
            if response.status_code == 404:
                continue
            response.raise_for_status()
            payload = response.json()
            if "results" not in payload:
                return payload

            best: dict[str, Any] | None = None
            best_score = 0.0
            for item in payload.get("results", []):
                candidate_title = item.get("display_name", "")
                similarity = difflib.SequenceMatcher(
                    a=target,
                    b=normalize_title(candidate_title),
                ).ratio()
                year_bonus = 0.05 if ref.year and str(item.get("publication_year", "")) == ref.year else 0.0
                score = similarity + year_bonus
                if score > best_score:
                    best_score = score
                    best = item
            if best and best_score >= 0.75:
                return best
        return None

    def best_pdf_url(self, work: dict[str, Any]) -> str:
        oa_locations = []
        for key in ("best_oa_location", "primary_location"):
            location = work.get(key)
            if location:
                oa_locations.append(location)
        oa_locations.extend(work.get("locations", []))
        for location in oa_locations:
            pdf_url = location.get("pdf_url")
            if pdf_url:
                return pdf_url
            landing = location.get("landing_page_url")
            if landing and landing.lower().endswith(".pdf"):
                return landing
        oa = work.get("open_access", {})
        if oa.get("oa_url") and str(oa["oa_url"]).lower().endswith(".pdf"):
            return oa["oa_url"]
        return ""

    def best_landing_url(self, work: dict[str, Any]) -> str:
        oa_locations = []
        for key in ("best_oa_location", "primary_location"):
            location = work.get(key)
            if location:
                oa_locations.append(location)
        oa_locations.extend(work.get("locations", []))
        for location in oa_locations:
            landing = location.get("landing_page_url")
            if landing:
                return landing
        oa = work.get("open_access", {})
        return oa.get("oa_url", "")

    def discover_fulltext_url(self, landing_url: str) -> str:
        if not landing_url:
            return ""
        known = self.known_pdf_transform(landing_url)
        if known:
            return known

        try:
            response = self.session.get(landing_url, timeout=REQUEST_TIMEOUT)
        except requests.RequestException:
            return ""

        content_type = response.headers.get("content-type", "").lower()
        if "pdf" in content_type:
            return response.url

        if "html" not in content_type and not response.text[:200].lstrip().startswith("<"):
            return ""

        soup = BeautifulSoup(response.text, "html.parser")
        for meta_name in ("citation_pdf_url", "dc.identifier", "og:url"):
            tag = soup.find("meta", attrs={"name": meta_name}) or soup.find("meta", attrs={"property": meta_name})
            if not tag:
                continue
            candidate = (tag.get("content") or "").strip()
            if candidate.lower().endswith(".pdf"):
                return urljoin(response.url, candidate)

        for link in soup.find_all("a", href=True):
            href = link["href"].strip()
            full = urljoin(response.url, href)
            text = " ".join(link.stripped_strings).lower()
            if full.lower().endswith(".pdf"):
                return full
            if "pdf" in text:
                transformed = self.known_pdf_transform(full) or full
                if transformed.lower().endswith(".pdf") or "openreview.net/pdf" in transformed:
                    return transformed

        return ""

    def known_pdf_transform(self, url: str) -> str:
        parsed = urlparse(url)
        if "arxiv.org" in parsed.netloc and parsed.path.startswith("/abs/"):
            return f"https://arxiv.org/pdf/{parsed.path.split('/abs/')[-1]}.pdf"
        if "openreview.net" in parsed.netloc and parsed.path == "/forum":
            return url.replace("/forum", "/pdf")
        if "openreview.net" in parsed.netloc and "/forum" in parsed.path:
            return url.replace("/forum", "/pdf")
        if "aclanthology.org" in parsed.netloc and not parsed.path.endswith(".pdf"):
            return url.rstrip("/") + ".pdf"
        if "cvf.com" in parsed.netloc and not url.lower().endswith(".pdf"):
            return ""
        if url.lower().endswith(".pdf"):
            return url
        return ""

    def github_archive_url(self, url: str) -> str:
        parsed = urlparse(url)
        if "github.com" not in parsed.netloc:
            return ""
        path = parsed.path.strip("/")
        parts = path.split("/")
        if len(parts) < 2:
            return ""
        owner, repo = parts[:2]
        return f"https://codeload.github.com/{owner}/{repo}/zip/refs/heads/main"

    def infer_file_type(self, url: str) -> str:
        lowered = url.lower()
        if lowered.endswith(".pdf") or "application/pdf" in lowered:
            return "pdf"
        if lowered.endswith(".zip"):
            return "zip"
        if "api.elsevier.com/content/article" in lowered or lowered.endswith(".xml"):
            return "xml"
        return "html"

    def download_resolution(self, ref: Reference, resolution: Resolution) -> None:
        try:
            response = self.session.get(
                resolution.fulltext_url,
                timeout=REQUEST_TIMEOUT,
                allow_redirects=True,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            resolution.status = "download_failed"
            resolution.note = f"Resolved URL could not be downloaded: {exc}"
            return

        content_type = response.headers.get("content-type", "").lower()
        detected_file_type = "html"
        if "pdf" in content_type or response.content.startswith(b"%PDF"):
            detected_file_type = "pdf"
        elif "zip" in content_type or response.content[:2] == b"PK":
            detected_file_type = "zip"
        elif "xml" in content_type or response.text.lstrip().startswith("<?xml") or response.text.lstrip().startswith("<full-text-retrieval-response"):
            detected_file_type = "xml"

        expected_file_type = resolution.file_type
        if expected_file_type == "pdf" and detected_file_type != "pdf":
            resolution.status = "download_failed"
            resolution.note = "Resolved URL returned HTML instead of a PDF, likely a landing or paywall page."
            resolution.file_type = detected_file_type
            return
        if expected_file_type == "zip" and detected_file_type != "zip":
            resolution.status = "download_failed"
            resolution.note = "Resolved URL returned non-archive content instead of a repository snapshot."
            resolution.file_type = detected_file_type
            return

        file_type = detected_file_type if detected_file_type != "html" or not expected_file_type else expected_file_type
        extension = {"pdf": ".pdf", "zip": ".zip", "html": ".html", "xml": ".xml"}.get(file_type, ".bin")
        filename = f"{ref.key}{extension}"
        target = self.files_dir / filename
        if file_type in {"html", "xml"}:
            target.write_text(response.text, encoding="utf-8")
        else:
            target.write_bytes(response.content)

        resolution.file_path = str(target)
        resolution.file_type = file_type
        resolution.status = "downloaded"
        resolution.fulltext_url = response.url

    def write_reports(self, results: list[Resolution]) -> None:
        manifest_json = self.output_dir / "manifest.json"
        manifest_csv = self.output_dir / "manifest.csv"
        summary_md = self.output_dir / "README.md"

        manifest_json.write_text(
            json.dumps([asdict(result) for result in results], indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        fieldnames = [
            "key",
            "title",
            "year",
            "authors",
            "original_doi",
            "resolved_doi",
            "arxiv_id",
            "matched_title",
            "match_score",
            "landing_url",
            "fulltext_url",
            "file_path",
            "file_type",
            "status",
            "note",
        ]
        with manifest_csv.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for result in results:
                row = {name: getattr(result, name) for name in fieldnames}
                writer.writerow(row)

        downloaded = sum(1 for result in results if result.status == "downloaded")
        unresolved = [result for result in results if result.status != "downloaded"]
        lines = [
            f"# Reference audit for `{self.tex_path.name}`",
            "",
            f"- Total references: {len(results)}",
            f"- Downloaded artifacts/full texts: {downloaded}",
            f"- Needs follow-up: {len(unresolved)}",
            "",
            "## Files",
            "",
            "- `parsed_references.json`: bibliography entries parsed from LaTeX.",
            "- `manifest.json` / `manifest.csv`: resolution metadata and download status.",
            f"- `files/`: downloaded PDFs, HTML pages, or repository archives.",
            "",
            "## Unresolved entries",
            "",
        ]
        if unresolved:
            for result in unresolved:
                lines.append(f"- `{result.key}`: {result.title} ({result.note})")
        else:
            lines.append("- None.")
        summary_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("tex_path", type=Path, help="Path to the LaTeX proposal")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory where manifests and downloads will be written",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    tex_path = args.tex_path.resolve()
    output_dir = args.output_dir
    if output_dir is None:
        output_dir = tex_path.parent / "references"
    else:
        output_dir = output_dir.resolve()

    downloader = Downloader(tex_path=tex_path, output_dir=output_dir)
    try:
        results = downloader.run()
    except Exception as exc:  # pragma: no cover - operational utility
        log(f"Failed: {exc}")
        return 1

    downloaded = sum(1 for result in results if result.status == "downloaded")
    log(f"Downloaded {downloaded}/{len(results)} references into {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
