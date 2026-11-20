"""Orquestrador do MEDSIM. Roda as etapas do pipeline a partir da raiz do projeto.

Uso:
    python main.py                  # roda todas as etapas, na ordem
    python main.py ingest --uf 22   # só a ingestão (UF repetível)
    python main.py --list           # lista as etapas
"""
import argparse
import logging
import sys
import time

from ingestion import ingestion

log = logging.getLogger("medsim")


def stage_ingest(args: argparse.Namespace) -> None:
    ingestion.run(args.uf)


# Ordem de execução. Novas etapas (tratamento, carga no Postgres, ...) entram aqui.
STAGES = {
    "ingest": stage_ingest,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("stage", nargs="?", choices=STAGES, help="etapa a rodar (padrão: todas)")
    parser.add_argument("--uf", type=int, action="append", help="código IBGE da UF (repetível). Padrão: 22")
    parser.add_argument("--list", action="store_true", help="lista as etapas e sai")
    args = parser.parse_args()

    if args.list:
        print("\n".join(STAGES))
        return 0

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    for name in [args.stage] if args.stage else STAGES:
        log.info("== etapa: %s ==", name)
        start = time.perf_counter()
        try:
            STAGES[name](args)
        except Exception:
            log.exception("etapa '%s' falhou", name)
            return 1
        log.info("== %s ok (%.1fs) ==", name, time.perf_counter() - start)
    return 0


if __name__ == "__main__":
    sys.exit(main())
