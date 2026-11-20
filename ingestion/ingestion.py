"""Ingestão do estoque de medicamentos (BNAFAR/HÓRUS) da API de Dados Abertos do Ministério da Saúde.

Uso:
    python ingestion/ingestion.py --uf 22            # Piauí
    python ingestion/ingestion.py --uf 22 --uf 35    # várias UFs
"""
import argparse
import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE_URL = "https://apidadosabertos.saude.gov.br/daf/estoque-medicamentos-bnafar-horus"
DATA_DIR = Path("data")
PAGE_SIZE = 100  # a API devolve no máximo 100 por página

log = logging.getLogger("ingestion")


def make_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=5,
        backoff_factor=1.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


def collect_stock(session: requests.Session, uf: int, **filters) -> list[dict]:
    """Pagina o endpoint até a API devolver uma página vazia ou incompleta."""
    records: list[dict] = []
    offset = 0
    while True:
        response = session.get(
            BASE_URL,
            params={"codigo_uf": uf, "limit": PAGE_SIZE, "offset": offset, **filters},
            timeout=60,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or "parametros" not in payload:
            raise ValueError(f"Formato inesperado da API: {str(payload)[:200]}")
        batch = payload["parametros"]
        records.extend(batch)
        log.info("UF %s: %d registros (offset %d)", uf, len(records), offset)
        if len(batch) < PAGE_SIZE:
            return records
        offset += PAGE_SIZE


def save_raw(records: list[dict], uf: int) -> Path | None:
    """Grava Parquet + manifesto em data/. Não grava nada se vazio ou se for igual à última coleta."""
    if not records:
        log.warning("UF %s: API não devolveu registros; nada gravado.", uf)
        return None

    body = "\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True) for r in records) + "\n"
    digest = hashlib.sha256(body.encode()).hexdigest()

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for manifest in DATA_DIR.glob(f"bnafar_uf{uf}_*.manifest.json"):
        if json.loads(manifest.read_text())["sha256"] == digest:
            log.info("UF %s: dados idênticos a %s; nada gravado.", uf, manifest.name)
            return None

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = DATA_DIR / f"bnafar_uf{uf}_{stamp}.parquet"
    pd.DataFrame(records).to_parquet(path, index=False)
    path.with_suffix(".manifest.json").write_text(
        json.dumps(
            {
                "source": BASE_URL,
                "codigo_uf": uf,
                "collected_at": datetime.now(timezone.utc).isoformat(),
                "n_records": len(records),
                "sha256": digest,
            },
            indent=2,
        )
    )
    log.info("UF %s: %d registros -> %s", uf, len(records), path)
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uf", type=int, action="append", default=None,
                        help="código IBGE da UF (repetível). Padrão: 22 (PI)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    session = make_session()
    for uf in args.uf or [22]:
        save_raw(collect_stock(session, uf), uf)


if __name__ == "__main__":
    main()
